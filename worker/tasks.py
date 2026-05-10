"""Celery 异步任务定义 — 文档生成任务占位。

Phase 3 实现，当前为占位桩。
"""

from worker.celery_app import app


@app.task(bind=True)
def generate_ppt_task(self, params: dict) -> dict:
    """占位 — Phase 3 实现 PPT 生成逻辑。"""
    return {"status": "completed", "task_id": self.request.id}


@app.task(bind=True)
def generate_word_task(self, params: dict) -> dict:
    """占位 — Phase 3 实现 Word 生成逻辑。"""
    return {"status": "completed", "task_id": self.request.id}


@app.task(bind=True)
def generate_pdf_task(self, params: dict) -> dict:
    """占位 — Phase 3 实现 PDF 生成逻辑。"""
    return {"status": "completed", "task_id": self.request.id}
