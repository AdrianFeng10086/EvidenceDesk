"""统一的业务错误类型与错误码。

接口错误返回结构：
    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    """可直接映射为 HTTP 响应的业务错误。"""

    status_code = 400
    code = "BAD_REQUEST"
    default_message = "请求无法处理"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "请求的资源不存在"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    default_message = "无权访问该资源"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    default_message = "当前状态不允许该操作"


class TooLargeError(AppError):
    status_code = 413
    code = "TOO_LARGE"
    default_message = "文件超过大小限制"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "UNSUPPORTED_FORMAT"
    default_message = "不支持的文件格式"


class ParseFailure(Exception):
    """解析失败：最终会写入文档版本的 parse_error_code / parse_error。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# 解析错误码（与 docs/architecture.md「错误处理」保持一致）
# ---------------------------------------------------------------------------

ERROR_ENCRYPTED = "ENCRYPTED"
ERROR_CORRUPTED = "CORRUPTED"
ERROR_NO_TEXT_LAYER = "NO_TEXT_LAYER"
ERROR_EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
ERROR_TOO_LARGE = "TOO_LARGE"
ERROR_TOO_MANY_PAGES = "TOO_MANY_PAGES"
ERROR_UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
ERROR_UNSUPPORTED_ENCODING = "UNSUPPORTED_ENCODING"
ERROR_INTERRUPTED = "INTERRUPTED"
ERROR_INTERNAL = "INTERNAL_ERROR"
