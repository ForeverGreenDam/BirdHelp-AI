class BirdHelpError(Exception):
    """Base exception with error code."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# ── 参数 / 业务错误 (1xxx) ──

class ValidationError(BirdHelpError):
    def __init__(self, message: str = "参数校验失败"):
        super().__init__(code=1001, message=message)


class QuotaInsufficientError(BirdHelpError):
    def __init__(self, message: str = "额度不足"):
        super().__init__(code=1002, message=message)


class MaterialFormatError(BirdHelpError):
    def __init__(self, message: str = "素材文件格式不支持"):
        super().__init__(code=1003, message=message)


# ── LLM 错误 (2xxx) ──

class LLMCallError(BirdHelpError):
    def __init__(self, message: str = "大模型调用失败"):
        super().__init__(code=2001, message=message)


class LLMParseError(BirdHelpError):
    def __init__(self, message: str = "大模型输出解析失败"):
        super().__init__(code=2002, message=message)


class EmbeddingError(BirdHelpError):
    def __init__(self, message: str = "嵌入向量化失败"):
        super().__init__(code=2003, message=message)


# ── 文件生成错误 (3xxx) ──

class FileGenerationError(BirdHelpError):
    def __init__(self, message: str = "文件生成失败"):
        super().__init__(code=3001, message=message)


class FileUploadError(BirdHelpError):
    def __init__(self, message: str = "文件上传失败"):
        super().__init__(code=3002, message=message)


class MaterialIngestionError(BirdHelpError):
    def __init__(self, message: str = "素材摄取失败"):
        super().__init__(code=3003, message=message)


# ── 语音 / OCR 错误 (4xxx) ──

class SpeechRecognitionError(BirdHelpError):
    def __init__(self, message: str = "语音识别失败"):
        super().__init__(code=4001, message=message)


# ── 内部错误 (5xxx) ──

class InternalError(BirdHelpError):
    def __init__(self, message: str = "内部未知错误"):
        super().__init__(code=5001, message=message)
