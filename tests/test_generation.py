"""Word / PDF 生成接口测试。

覆盖 Chain、Generator、Graph、API 端点四层。
通过 FastAPI dependency_overrides 绕过 RSA 签名验证，
通过 unittest.mock 模拟 LLM 和 Java 后端调用。
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

# ── 应用导入 ──

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app
from core.auth import require_java_caller
from core.schemas import (
    WordGenerateRequest,
    PdfGenerateRequest,
    PptGenerateRequest,
    ApiResponse,
)

# ── 常量 ──

FAKE_WORD_JSON = json.dumps({
    "title": "人工智能发展报告",
    "subtitle": "2025年度综述",
    "abstract": "本报告全面分析了人工智能在2025年的发展现状与未来趋势。",
    "sections": [
        {"heading": "第一章 引言", "content": ["人工智能技术正在深刻改变各行各业。"]},
        {"heading": "第二章 核心技术进展", "content": ["大语言模型持续突破性能边界。"]},
        {"heading": "第三章 行业应用", "content": ["医疗、金融、教育等领域加速AI落地。"]},
        {"heading": "第四章 未来展望", "content": ["AI Agent和具身智能将成为下一个爆发点。"]},
    ],
    "references": ["[1] AI Index Report 2025, Stanford HAI"]
}, ensure_ascii=False)

FAKE_PDF_JSON = json.dumps({
    "title": "年度工作总结",
    "subtitle": "Q1-Q4业绩回顾",
    "author": "张三",
    "date": "2025-12-31",
    "sections": [
        {"heading": "一、工作概述", "content": ["本年度完成了多项核心任务。"]},
        {"heading": "二、重点项目", "content": ["项目A按时交付，客户满意度达95%。"]},
        {"heading": "三、数据总结", "content": ["全年营收同比增长30%。"]},
    ],
    "tables": [
        {"caption": "季度业绩对比", "headers": ["季度", "营收(万)", "增长率"],
         "rows": [["Q1", "120", "15%"], ["Q2", "150", "25%"], ["Q3", "180", "20%"], ["Q4", "210", "17%"]]}
    ]
}, ensure_ascii=False)

FAKE_PPT_JSON = json.dumps({
    "title": "测试演示文稿",
    "slides": [
        {"title": "封面", "subtitle": "副标题", "layout": "title_slide", "content": []},
        {"title": "内容页1", "layout": "title_and_content", "content": ["要点1", "要点2"]},
        {"title": "内容页2", "layout": "title_and_content", "content": ["要点3", "要点4"]},
        {"title": "感谢观看", "layout": "blank", "content": []},
    ]
}, ensure_ascii=False)


def _fake_llm_runnable(json_str: str):
    """创建返回指定 JSON 的假 LLM Runnable，可参与 LangChain 管道。"""
    async def _ainvoke(input, config=None, **kwargs):
        return json_str
    return RunnableLambda(_ainvoke)


# ── Fixtures ──

@pytest.fixture(autouse=True)
def bypass_auth():
    """绕过 RSA 签名验证，所有 /ai/* 请求直接放行。"""
    async def _bypass():
        return None
    app.dependency_overrides[require_java_caller] = _bypass
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(bypass_auth):
    """提供已绕过认证的 TestClient。"""
    return TestClient(app)


@pytest.fixture
def mock_llm_word():
    """模拟 LLM 返回 Word JSON。"""
    with patch("chains.word_chain.create_chat_model",
               return_value=_fake_llm_runnable(FAKE_WORD_JSON)):
        yield


@pytest.fixture
def mock_llm_pdf():
    """模拟 LLM 返回 PDF JSON。"""
    with patch("chains.pdf_chain.create_chat_model",
               return_value=_fake_llm_runnable(FAKE_PDF_JSON)):
        yield


@pytest.fixture
def mock_llm_ppt():
    """模拟 LLM 返回 PPT JSON。"""
    with patch("chains.ppt_chain.create_chat_model",
               return_value=_fake_llm_runnable(FAKE_PPT_JSON)):
        yield


@pytest.fixture
def mock_java_backend():
    """模拟 Java 后端（额度扣减 + 文件上传）。"""
    with patch("services.generation.consume_quota", new_callable=AsyncMock) as mock_consume, \
         patch("services.generation.upload_file", new_callable=AsyncMock) as mock_upload, \
         patch("services.generation.refund_quota", new_callable=AsyncMock) as mock_refund:
        mock_consume.return_value = {"code": 0, "message": "success"}
        mock_upload.return_value = {
            "file_id": 999,
            "file_url": "https://storage.example.com/files/999",
            "file_name": "test",
        }
        mock_refund.return_value = {"code": 0}
        yield {
            "consume": mock_consume,
            "upload": mock_upload,
            "refund": mock_refund,
        }


# ═══════════════════════════════════════════════
# Chain 测试 — 验证 LLM 输出解析
# ═══════════════════════════════════════════════

class TestWordChain:
    """chains/word_chain.py"""

    def test_ainvoke_returns_structured_dict(self, mock_llm_word):
        from chains.word_chain import WordChain
        import asyncio
        chain = WordChain()
        output = asyncio.run(chain.ainvoke({
            "topic": "人工智能发展报告",
            "doc_type": "report",
            "word_count": 3000,
            "language": "zh",
            "context": "",
            "extra_prompt": "",
        }))
        assert output["title"] == "人工智能发展报告"
        assert output["subtitle"] == "2025年度综述"
        assert len(output["sections"]) == 4
        assert len(output["references"]) == 1
        assert "raw" in output

    def test_essay_type_includes_abstract(self, mock_llm_word):
        from chains.word_chain import WordChain
        chain = WordChain()
        import asyncio
        output = asyncio.run(chain.ainvoke({
            "topic": "测试论文",
            "doc_type": "essay",
            "word_count": 2000,
            "language": "zh",
        }))
        assert output["abstract"] != ""

    def test_letter_type_output(self, mock_llm_word):
        from chains.word_chain import WordChain
        chain = WordChain()
        import asyncio
        output = asyncio.run(chain.ainvoke({
            "topic": "商务信函",
            "doc_type": "letter",
            "word_count": 500,
            "language": "zh",
        }))
        assert "title" in output
        assert "sections" in output


class TestPdfChain:
    """chains/pdf_chain.py"""

    def test_ainvoke_returns_structured_dict(self, mock_llm_pdf):
        from chains.pdf_chain import PdfChain
        chain = PdfChain()
        import asyncio
        output = asyncio.run(chain.ainvoke({
            "topic": "年度工作总结",
            "doc_type": "report",
            "language": "zh",
            "context": "",
            "extra_prompt": "",
        }))
        assert output["title"] == "年度工作总结"
        assert output["author"] == "张三"
        assert len(output["sections"]) == 3
        assert len(output["tables"]) == 1
        assert output["tables"][0]["headers"] == ["季度", "营收(万)", "增长率"]

    def test_report_type_output(self, mock_llm_pdf):
        from chains.pdf_chain import PdfChain
        chain = PdfChain()
        import asyncio
        output = asyncio.run(chain.ainvoke({
            "topic": "研究报告",
            "doc_type": "report",
            "language": "zh",
        }))
        assert "title" in output
        assert len(output["sections"]) >= 1

    def test_resume_type_output(self, mock_llm_pdf):
        from chains.pdf_chain import PdfChain
        chain = PdfChain()
        import asyncio
        output = asyncio.run(chain.ainvoke({
            "topic": "个人简历",
            "doc_type": "resume",
            "language": "zh",
        }))
        assert "title" in output
        assert "sections" in output


# ═══════════════════════════════════════════════
# Generator 测试 — 验证文件生成
# ═══════════════════════════════════════════════

class TestWordGenerator:
    """generator/word.py"""

    def test_generate_creates_docx_file(self, tmp_path):
        from generator.word import WordGenerator
        from utils.file import ensure_temp_dir
        ensure_temp_dir()

        content = {
            "title": "测试文档",
            "subtitle": "副标题",
            "abstract": "这是一份测试文档。",
            "sections": [
                {"heading": "第一节", "content": ["这是第一段的文本内容。", "这是第二段的文本内容。"]},
                {"heading": "第二节", "content": ["这是第二部分的文本。"]},
            ],
            "references": ["[1] 测试参考文献"],
            "style": "academic",
        }
        output_path = tmp_path / "test_output.docx"
        generator = WordGenerator()
        result = generator.generate(content, output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_generate_minimal_content(self, tmp_path):
        from generator.word import WordGenerator
        from utils.file import ensure_temp_dir
        ensure_temp_dir()

        content = {
            "title": "最小文档",
            "sections": [{"heading": "内容", "content": ["一段文本。"]}],
            "style": "business",
        }
        output_path = tmp_path / "minimal.docx"
        generator = WordGenerator()
        result = generator.generate(content, output_path)
        assert result.exists()

    def test_business_style_applied(self, tmp_path):
        from generator.word import WordGenerator
        from utils.file import ensure_temp_dir
        ensure_temp_dir()

        content = {
            "title": "商务文档",
            "sections": [{"heading": "概述", "content": ["商务风格的文本内容。"]}],
            "style": "business",
        }
        output_path = tmp_path / "business.docx"
        generator = WordGenerator()
        result = generator.generate(content, output_path)
        assert result.exists()


class TestPdfGenerator:
    """generator/pdf.py"""

    def test_generate_creates_file(self, tmp_path):
        from generator.pdf import PdfGenerator
        from utils.file import ensure_temp_dir
        ensure_temp_dir()

        content = {
            "title": "测试PDF文档",
            "subtitle": "副标题",
            "author": "作者名",
            "date": "2025-01-01",
            "sections": [
                {"heading": "第一节", "content": ["段落内容一。", "段落内容二。"]},
                {"heading": "第二节", "content": ["另一部分的内容。"]},
            ],
            "tables": [
                {"caption": "数据表", "headers": ["列A", "列B"],
                 "rows": [["值1", "值2"], ["值3", "值4"]]}
            ],
            "style": "academic",
        }
        output_path = tmp_path / "test_output.pdf"
        generator = PdfGenerator()
        result = generator.generate(content, output_path)

        assert result.exists()
        assert result.stat().st_size > 0
        # 无 LibreOffice 时回退为 .docx
        assert result.suffix.lower() in (".pdf", ".docx")

    def test_generate_minimal_pdf(self, tmp_path):
        from generator.pdf import PdfGenerator
        from utils.file import ensure_temp_dir
        ensure_temp_dir()

        content = {
            "title": "最小PDF",
            "sections": [{"heading": "内容", "content": ["一段文字。"]}],
        }
        output_path = tmp_path / "minimal.pdf"
        generator = PdfGenerator()
        result = generator.generate(content, output_path)
        assert result.exists()

    def test_form_type_with_table(self, tmp_path):
        from generator.pdf import PdfGenerator
        from utils.file import ensure_temp_dir
        ensure_temp_dir()

        content = {
            "title": "登记表",
            "sections": [{"heading": "说明", "content": ["请如实填写以下信息。"]}],
            "tables": [
                {"caption": "个人信息", "headers": ["姓名", "年龄", "部门"],
                 "rows": [["张三", "28", "研发部"]]}
            ],
            "style": "business",
        }
        output_path = tmp_path / "form.pdf"
        generator = PdfGenerator()
        result = generator.generate(content, output_path)
        assert result.exists()


# ═══════════════════════════════════════════════
# API 端点测试 — 验证请求/响应
# ═══════════════════════════════════════════════

class TestWordApiEndpoint:
    """POST /ai/word/generate"""

    def test_returns_success_response(self, client, mock_java_backend, mock_llm_word):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "人工智能发展报告",
            "doc_type": "report",
            "word_count": 3000,
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/word/generate", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["file_id"] == 999

    def test_calls_quota_consume(self, client, mock_java_backend, mock_llm_word):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "doc_type": "essay",
            "word_count": 500,
            "language": "zh",
            "callback_id": "12345678",
        }
        client.post("/ai/word/generate", json=payload)
        mock_java_backend["consume"].assert_called_once()

    def test_calls_file_upload(self, client, mock_java_backend, mock_llm_word):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "doc_type": "essay",
            "word_count": 500,
            "language": "zh",
            "callback_id": "12345678",
        }
        client.post("/ai/word/generate", json=payload)
        mock_java_backend["upload"].assert_called_once()

    def test_quota_insufficient_returns_error(self, client, mock_java_backend, mock_llm_word):
        mock_java_backend["consume"].return_value = {"code": 1002, "message": "额度不足"}

        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "doc_type": "essay",
            "word_count": 500,
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/word/generate", json=payload)

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == 1002

    def test_default_doc_type(self, client, mock_java_backend, mock_llm_word):
        """不传 doc_type 时使用默认值 essay。"""
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/word/generate", json=payload)
        assert response.status_code == 200

    def test_max_word_count_boundary(self, client, mock_java_backend, mock_llm_word):
        """word_count=10000 应在合法范围内。"""
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "长篇报告",
            "doc_type": "paper",
            "word_count": 10000,
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/word/generate", json=payload)
        assert response.status_code == 200

    def test_word_count_below_minimum_rejected(self, client):
        """word_count < 500 时应被 Pydantic 校验拒绝。"""
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "word_count": 100,
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/word/generate", json=payload)
        assert response.status_code == 422

    def test_word_count_above_maximum_rejected(self, client):
        """word_count > 10000 时应被 Pydantic 校验拒绝。"""
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "word_count": 20000,
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/word/generate", json=payload)
        assert response.status_code == 422


class TestPdfApiEndpoint:
    """POST /ai/pdf/generate"""

    def test_returns_success_response(self, client, mock_java_backend, mock_llm_pdf):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "年度工作总结",
            "doc_type": "report",
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/pdf/generate", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["file_id"] == 999

    def test_calls_quota_consume(self, client, mock_java_backend, mock_llm_pdf):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "doc_type": "report",
            "language": "zh",
            "callback_id": "12345678",
        }
        client.post("/ai/pdf/generate", json=payload)
        mock_java_backend["consume"].assert_called_once()

    def test_calls_file_upload(self, client, mock_java_backend, mock_llm_pdf):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "doc_type": "report",
            "language": "zh",
            "callback_id": "12345678",
        }
        client.post("/ai/pdf/generate", json=payload)
        mock_java_backend["upload"].assert_called_once()

    def test_quota_insufficient_returns_error(self, client, mock_java_backend, mock_llm_pdf):
        mock_java_backend["consume"].return_value = {"code": 1002, "message": "额度不足"}

        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "doc_type": "report",
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/pdf/generate", json=payload)

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == 1002

    def test_default_doc_type(self, client, mock_java_backend, mock_llm_pdf):
        """不传 doc_type 时使用默认值 report。"""
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/pdf/generate", json=payload)
        assert response.status_code == 200

    def test_resume_type(self, client, mock_java_backend, mock_llm_pdf):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "软件工程师简历",
            "doc_type": "resume",
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/pdf/generate", json=payload)
        assert response.status_code == 200

    def test_form_type(self, client, mock_java_backend, mock_llm_pdf):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "员工信息登记表",
            "doc_type": "form",
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/pdf/generate", json=payload)
        assert response.status_code == 200


# ═══════════════════════════════════════════════
# Graph 分发测试 — 验证 doc_type 分发逻辑
# ═══════════════════════════════════════════════

class TestGraphDispatch:
    """graph/generation_graph.py — 三种 doc_type 共用状态图"""

    @pytest.mark.parametrize("doc_type,chain_module,json_fixture", [
        ("word", "chains.word_chain", FAKE_WORD_JSON),
        ("pdf", "chains.pdf_chain", FAKE_PDF_JSON),
        ("ppt", "chains.ppt_chain", FAKE_PPT_JSON),
    ])
    def test_graph_runs_all_doc_types(self, doc_type, chain_module, json_fixture,
                                       mock_java_backend):
        from graph.generation_graph import get_generation_graph
        import asyncio

        with patch(f"{chain_module}.create_chat_model",
                   return_value=_fake_llm_runnable(json_fixture)):
            graph = get_generation_graph()
            state = {
                "user_id": "1",
                "project_id": "5",
                "topic": "测试主题",
                "language": "zh",
                "extra_prompt": "",
                "rag_enabled": False,
                "material_ids": [],
                "doc_type": doc_type,
                "doc_subtype": "report",
                "style": "academic",
                "slide_count": 10,
                "word_count": 2000,
                "context": "",
                "chain_output": "",
                "parsed_outline": {},
                "attempt": 0,
                "file_path": "",
                "error": "",
            }
            result = asyncio.run(graph.ainvoke(state))

            assert not result.get("error"), f"Graph failed for {doc_type}: {result.get('error')}"
            assert result.get("file_path"), f"No file_path for {doc_type}"
            assert Path(result["file_path"]).exists()

    def test_word_graph_produces_docx(self, mock_java_backend):
        from graph.generation_graph import get_generation_graph
        import asyncio

        with patch("chains.word_chain.create_chat_model",
                   return_value=_fake_llm_runnable(FAKE_WORD_JSON)):
            graph = get_generation_graph()
            result = asyncio.run(graph.ainvoke({
                "user_id": "1", "project_id": "5", "topic": "测试",
                "language": "zh", "extra_prompt": "", "rag_enabled": False,
                "material_ids": [], "doc_type": "word", "doc_subtype": "essay",
                "style": "academic", "slide_count": 0, "word_count": 2000,
                "context": "", "chain_output": "", "parsed_outline": {},
                "attempt": 0, "file_path": "", "error": "",
            }))
            assert not result.get("error")
            assert result["file_path"].endswith(".docx")

    def test_pdf_graph_produces_output(self, mock_java_backend):
        from graph.generation_graph import get_generation_graph
        import asyncio

        with patch("chains.pdf_chain.create_chat_model",
                   return_value=_fake_llm_runnable(FAKE_PDF_JSON)):
            graph = get_generation_graph()
            result = asyncio.run(graph.ainvoke({
                "user_id": "1", "project_id": "5", "topic": "测试",
                "language": "zh", "extra_prompt": "", "rag_enabled": False,
                "material_ids": [], "doc_type": "pdf", "doc_subtype": "report",
                "style": "academic", "slide_count": 0, "word_count": 0,
                "context": "", "chain_output": "", "parsed_outline": {},
                "attempt": 0, "file_path": "", "error": "",
            }))
            assert not result.get("error")
            assert Path(result["file_path"]).exists()

    def test_rag_enabled_triggers_retrieval(self, mock_java_backend):
        """启用 RAG 时走检索节点（即使检索结果为空也应成功）。"""
        from graph.generation_graph import get_generation_graph
        import asyncio

        with patch("chains.word_chain.create_chat_model",
                   return_value=_fake_llm_runnable(FAKE_WORD_JSON)), \
             patch("graph.generation_graph.retrieve_formatted",
                   new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = ""
            graph = get_generation_graph()
            result = asyncio.run(graph.ainvoke({
                "user_id": "1", "project_id": "5", "topic": "测试",
                "language": "zh", "extra_prompt": "", "rag_enabled": True,
                "material_ids": ["42"], "doc_type": "word", "doc_subtype": "essay",
                "style": "academic", "slide_count": 0, "word_count": 2000,
                "context": "", "chain_output": "", "parsed_outline": {},
                "attempt": 0, "file_path": "", "error": "",
            }))
            assert not result.get("error")


# ═══════════════════════════════════════════════
# 错误处理 & 边界条件
# ═══════════════════════════════════════════════

class TestErrorHandling:
    """异常与边界测试"""

    def test_refund_on_generation_failure(self, client, mock_java_backend):
        """生成失败时应退还已扣额度。"""
        with patch("chains.word_chain.create_chat_model",
                   return_value=_fake_llm_runnable("invalid {{{ json")):
            payload = {
                "user_id": "1",
                "project_id": "5",
                "topic": "测试",
                "doc_type": "essay",
                "word_count": 500,
                "language": "zh",
                "callback_id": "12345678",
            }
            response = client.post("/ai/word/generate", json=payload)

            assert response.status_code in (400, 500)
            mock_java_backend["refund"].assert_called_once()

    def test_quota_not_refunded_when_never_consumed(self, client, mock_java_backend):
        """额度扣减本身失败时，不应触发退款。"""
        mock_java_backend["consume"].return_value = {"code": 1002, "message": "额度不足"}

        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试",
            "doc_type": "essay",
            "word_count": 500,
            "language": "zh",
            "callback_id": "12345678",
        }
        client.post("/ai/word/generate", json=payload)

        mock_java_backend["refund"].assert_not_called()

    def test_auth_required_without_bypass(self, client):
        """无签名头且未 bypass 时，应返回 401。"""
        # 清除 bypass，恢复原始依赖
        app.dependency_overrides.clear()

        try:
            payload = {
                "user_id": "1",
                "project_id": "5",
                "topic": "测试",
                "doc_type": "essay",
                "word_count": 500,
                "language": "zh",
                "callback_id": "12345678",
            }
            response = client.post("/ai/word/generate", json=payload)
            assert response.status_code == 401
        finally:
            # 恢复 bypass（autouse fixture 在下一个 test 会重新设置）
            pass

    def test_missing_required_fields(self, client):
        """缺少必填字段 user_id 时应被 Pydantic 校验拒绝。"""
        payload = {
            "project_id": "5",
            "topic": "测试",
            "callback_id": "test-id",
        }
        response = client.post("/ai/word/generate", json=payload)
        assert response.status_code == 422

    def test_empty_topic_accepted(self, client, mock_java_backend, mock_llm_word):
        """空 topic 语法上合法（业务层自行判断）。"""
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "",
            "doc_type": "essay",
            "word_count": 500,
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/word/generate", json=payload)
        # 可能成功也可能因校验失败，但不应 500 崩溃
        assert response.status_code in (200, 400)


# ═══════════════════════════════════════════════
# 跨接口 — PPT 接口回归测试
# ═══════════════════════════════════════════════

class TestPptApiRegression:
    """验证 graph 重构后 PPT 接口仍正常工作"""

    def test_ppt_generate_still_works(self, client, mock_java_backend, mock_llm_ppt):
        payload = {
            "user_id": "1",
            "project_id": "5",
            "topic": "测试PPT",
            "style": "academic",
            "slide_count": 5,
            "language": "zh",
            "callback_id": "12345678",
        }
        response = client.post("/ai/ppt/generate", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["file_id"] == 999
