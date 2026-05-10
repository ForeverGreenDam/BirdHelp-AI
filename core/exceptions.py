"""统一异常体系，按模块分层错误码。

错误码规则:
  1xxx: 参数 / 业务错误
  2xxx: LLM / 嵌入模型错误
  3xxx: 文件生成 / 上传 / 摄取错误
  4xxx: 语音 / OCR 错误
  5xxx: 内部未知错误
"""


class BirdHelpError(Exception):
    """所有业务异常的基类，携带错误码与可读消息。"""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# ── 参数 / 业务错误 (1xxx) ──

class ValidationError(BirdHelpError):
    """请求参数校验失败。"""
    def __init__(self, message: str = "参数校验失败"):
        super().__init__(code=1001, message=message)


class QuotaInsufficientError(BirdHelpError):
    """用户额度不足。"""
    def __init__(self, message: str = "额度不足"):
        super().__init__(code=1002, message=message)


class MaterialFormatError(BirdHelpError):
    """上传的素材文件格式不支持。"""
    def __init__(self, message: str = "素材文件格式不支持"):
        super().__init__(code=1003, message=message)


# ── LLM 错误 (2xxx) ──

class LLMCallError(BirdHelpError):
    """调用大模型 API 失败（网络、限流、服务异常等）。"""
    def __init__(self, message: str = "大模型调用失败"):
        super().__init__(code=2001, message=message)


class LLMParseError(BirdHelpError):
    """大模型返回内容无法解析为预期的结构化 JSON。"""
    def __init__(self, message: str = "大模型输出解析失败"):
        super().__init__(code=2002, message=message)


class EmbeddingError(BirdHelpError):
    """文本嵌入向量化失败。"""
    def __init__(self, message: str = "嵌入向量化失败"):
        super().__init__(code=2003, message=message)


# ── 文件生成错误 (3xxx) ──

class FileGenerationError(BirdHelpError):
    """Office 文件（PPT/Word/PDF）生成过程失败。"""
    def __init__(self, message: str = "文件生成失败"):
        super().__init__(code=3001, message=message)


class FileUploadError(BirdHelpError):
    """生成结果上传到 Java 后端失败。"""
    def __init__(self, message: str = "文件上传失败"):
        super().__init__(code=3002, message=message)


class MaterialIngestionError(BirdHelpError):
    """RAG 素材解析 / 切分 / 入库失败。"""
    def __init__(self, message: str = "素材摄取失败"):
        super().__init__(code=3003, message=message)


# ── 语音 / OCR 错误 (4xxx) ──

class SpeechRecognitionError(BirdHelpError):
    """语音转文字失败。"""
    def __init__(self, message: str = "语音识别失败"):
        super().__init__(code=4001, message=message)


# ── 内部错误 (5xxx) ──

class InternalError(BirdHelpError):
    """未分类的内部错误，通常对应 HTTP 500。"""
    def __init__(self, message: str = "内部未知错误"):
        super().__init__(code=5001, message=message)
