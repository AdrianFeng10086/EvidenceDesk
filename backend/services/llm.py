"""
LLM 客户端封装 - OpenAI 兼容接口（当前为 DeepSeek）

所有配置来自环境变量：
    LLM_MODEL / LLM_API_KEY / LLM_BASE_URL
    VISION_MODEL / VISION_API_KEY / VISION_BASE_URL（未设置时回退到 LLM_*）
    LLM_TEMPERATURE / LLM_MAX_TOKENS / LLM_TIMEOUT_SECONDS
"""

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, OpenAI

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"


def llm_model() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


def vision_model() -> str:
    return os.getenv("VISION_MODEL") or llm_model()


def default_params() -> Dict[str, Any]:
    """生成参数默认值"""
    return {
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
    }


def _client_kwargs(vision: bool) -> Dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
    if vision:
        api_key = os.getenv("VISION_API_KEY") or api_key
        base_url = os.getenv("VISION_BASE_URL") or base_url

    if not api_key:
        raise RuntimeError("未配置 LLM_API_KEY" + (" / VISION_API_KEY" if vision else ""))

    return {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
    }


@lru_cache(maxsize=2)
def get_llm_client(vision: bool = False) -> OpenAI:
    """同步客户端（脚本、后台任务）"""
    return OpenAI(**_client_kwargs(vision))


@lru_cache(maxsize=2)
def get_async_llm_client(vision: bool = False) -> AsyncOpenAI:
    """异步客户端（FastAPI 路由、SSE 流式输出）"""
    return AsyncOpenAI(**_client_kwargs(vision))


def chat(messages: List[Dict[str, Any]], model: Optional[str] = None, **kwargs: Any) -> str:
    """单轮调用，返回文本内容"""
    params = {**default_params(), **kwargs}
    resp = get_llm_client().chat.completions.create(
        model=model or llm_model(), messages=messages, **params
    )
    return resp.choices[0].message.content or ""
