"""
向量化客户端 - Cloudflare Workers AI

调用格式:
    POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}
    Authorization: Bearer {API_TOKEN}
    {"text": ["文本1", "文本2"]}

响应:
    {"result": {"data": [[...], [...]], "shape": [2, 1024]}, "success": true, "errors": []}
"""

import hashlib
import math
import os
from collections import Counter
from typing import Any, Dict, List, Optional

import httpx

from services.tokenizer import tokenize

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4/accounts"

# 单次请求的文本数量上限，超过时自动分批
DEFAULT_BATCH_SIZE = 100


class EmbeddingError(RuntimeError):
    """向量化调用失败"""


class CloudflareEmbedding:
    """Cloudflare Workers AI 向量化客户端

    在 Chroma 中使用请通过 CloudflareChromaEmbeddingFunction 适配。
    """

    def __init__(
        self,
        account_id: Optional[str] = None,
        api_token: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
        timeout: Optional[float] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = api_token or os.getenv("EMBEDDING_API_KEY")
        self.model = model or os.getenv("EMBEDDING_MODEL", "@cf/qwen/qwen3-embedding-0.6b")
        self.dimension = dimension or int(os.getenv("EMBEDDING_DIMENSION", "1024"))
        self.timeout = timeout or float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30"))
        self.batch_size = batch_size

        if not self.account_id:
            raise EmbeddingError("未配置 CLOUDFLARE_ACCOUNT_ID")
        if not self.api_token:
            raise EmbeddingError("未配置 EMBEDDING_API_KEY")

        self.url = f"{CLOUDFLARE_API_BASE}/{self.account_id}/ai/run/{self.model}"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # 同步接口
    # ------------------------------------------------------------------

    def embed(self, texts: List[str]) -> List[List[float]]:
        """批量向量化，返回与输入顺序一致的向量列表"""
        if not texts:
            return []

        embeddings: List[List[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for batch in self._batches(texts):
                resp = client.post(self.url, headers=self.headers, json={"text": batch})
                embeddings.extend(self._parse(resp, len(batch)))
        return embeddings

    def embed_one(self, text: str) -> List[float]:
        """单条文本向量化（如检索查询）"""
        return self.embed([text])[0]

    # ------------------------------------------------------------------
    # 异步接口（供 FastAPI 路由使用）
    # ------------------------------------------------------------------

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        embeddings: List[List[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for batch in self._batches(texts):
                resp = await client.post(self.url, headers=self.headers, json={"text": batch})
                embeddings.extend(self._parse(resp, len(batch)))
        return embeddings

    async def aembed_one(self, text: str) -> List[float]:
        return (await self.aembed([text]))[0]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _batches(self, texts: List[str]):
        for i in range(0, len(texts), self.batch_size):
            yield texts[i : i + self.batch_size]

    def _parse(self, resp: httpx.Response, expected_count: int) -> List[List[float]]:
        try:
            payload = resp.json()
        except ValueError:
            raise EmbeddingError(f"HTTP {resp.status_code}: 非 JSON 响应 {resp.text[:200]}")

        if resp.status_code != 200 or not payload.get("success", False):
            errors = payload.get("errors") or resp.text[:200]
            raise EmbeddingError(f"HTTP {resp.status_code}: {errors}")

        data = (payload.get("result") or {}).get("data")
        if not isinstance(data, list) or len(data) != expected_count:
            raise EmbeddingError(f"返回向量数量异常: 期望 {expected_count}, 实际 {len(data or [])}")

        for vector in data:
            if len(vector) != self.dimension:
                raise EmbeddingError(
                    f"向量维度不匹配: 期望 {self.dimension}, 实际 {len(vector)}"
                    "（请检查 EMBEDDING_DIMENSION）"
                )
        return data


try:
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
    from chromadb.utils.embedding_functions import register_embedding_function

    @register_embedding_function
    class CloudflareChromaEmbeddingFunction(EmbeddingFunction[Documents]):
        """Chroma 1.x EmbeddingFunction 适配器

        Chroma 会把 get_config() 持久化到磁盘，因此配置中只保存模型和维度，
        账户 ID 与 Token 始终从环境变量读取，避免密钥落盘。
        """

        def __init__(self, model: Optional[str] = None, dimension: Optional[int] = None):
            self._client = CloudflareEmbedding(model=model, dimension=dimension)

        def __call__(self, input: Documents) -> Embeddings:
            return self._client.embed(list(input))

        @staticmethod
        def name() -> str:
            return "cloudflare_workers_ai"

        def default_space(self) -> str:
            return "cosine"

        def get_config(self) -> Dict[str, Any]:
            return {"model": self._client.model, "dimension": self._client.dimension}

        @staticmethod
        def build_from_config(config: Dict[str, Any]) -> "CloudflareChromaEmbeddingFunction":
            return CloudflareChromaEmbeddingFunction(
                model=config.get("model"), dimension=config.get("dimension")
            )

except ImportError:  # 未安装 chromadb 时，仅提供纯 HTTP 客户端
    pass


class LocalHashEmbedding:
    """确定性本地哈希向量。

    只用于开发/测试或无外部模型凭据时的降级路径。它把中文单字、二元组
    与英文词项哈希到固定维度，能保证“同一文本得到同一向量”，便于离线
    验证索引与检索链路；语义泛化能力弱于真实嵌入模型。
    """

    provider = "local"

    def __init__(self, dimension: int = 1024, model: str = "local-hash-v1"):
        self.dimension = int(dimension)
        self.model = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_one(self, text: str) -> List[float]:
        return self._embed_one(text)

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        return self.embed(texts)

    async def aembed_one(self, text: str) -> List[float]:
        return self.embed_one(text)

    def _embed_one(self, text: str) -> List[float]:
        vector = [0.0] * self.dimension
        counts = Counter(tokenize(text))
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            sign = 1.0 if (value >> 63) & 1 else -1.0
            # 次线性词频，避免长文本被重复词项主导
            vector[index] += sign * (1.0 + math.log(count))

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]


EmbeddingBackend = Any


def get_embedding_backend() -> EmbeddingBackend:
    """按配置返回嵌入后端。

    - local/hash: 本地确定性向量，离线可用
    - cloudflare: Cloudflare Workers AI（需要账户 ID 与 Token）
    - sentence-transformers: 可选本地模型（若安装）
    """
    from core.config import get_settings

    settings = get_settings()
    provider = (settings.embedding_provider or "cloudflare").strip().lower()
    model = settings.embedding_model
    dimension = settings.embedding_dimension

    if provider in {"local", "hash", "dev", "offline"}:
        return LocalHashEmbedding(dimension=dimension, model="local-hash-v1")

    if provider in {"cloudflare", "cf", "workers-ai"}:
        return CloudflareEmbedding(
            model=model,
            dimension=dimension,
            batch_size=settings.embedding_batch_size,
        )

    if provider in {"sentence-transformers", "sentence_transformers", "st"}:
        from sentence_transformers import SentenceTransformer

        class _SentenceTransformerBackend:
            provider = "sentence-transformers"

            def __init__(self) -> None:
                self.model = model
                self._model = SentenceTransformer(model)

            def embed(self, texts: List[str]) -> List[List[float]]:
                vectors = self._model.encode(texts, normalize_embeddings=True)
                return [list(map(float, vector)) for vector in vectors]

            def embed_one(self, text: str) -> List[float]:
                return self.embed([text])[0]

            async def aembed(self, texts: List[str]) -> List[List[float]]:
                return self.embed(texts)

            async def aembed_one(self, text: str) -> List[float]:
                return self.embed_one(text)

        return _SentenceTransformerBackend()

    raise EmbeddingError(f"未知的 EMBEDDING_PROVIDER: {provider}")


_current_backend: Optional[EmbeddingBackend] = None


def get_current_embedding_backend() -> EmbeddingBackend:
    """进程内复用嵌入后端（配置变化后重启生效）。"""
    global _current_backend
    if _current_backend is None:
        _current_backend = get_embedding_backend()
    return _current_backend


def reset_embedding_backend() -> None:
    global _current_backend
    _current_backend = None


def embed_texts(texts: List[str]) -> List[List[float]]:
    return get_current_embedding_backend().embed(texts)


def embed_query(text: str) -> List[float]:
    return get_current_embedding_backend().embed_one(text)


_default_client: Optional[CloudflareEmbedding] = None


def get_embedding_client() -> CloudflareEmbedding:
    """获取全局共享的 Cloudflare 向量化客户端（按环境变量初始化）"""
    global _default_client
    if _default_client is None:
        _default_client = CloudflareEmbedding()
    return _default_client
