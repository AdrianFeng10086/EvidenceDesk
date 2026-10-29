"""
对话流式接口 (SSE)

Day 2 范围：
- 真实模型文本流（text_delta）接入 DeepSeek（OpenAI 兼容接口）
- 用明确标注的样例证据展示折叠证据卡（tool_started/tool_finished + claim_ready）
  样例证据不是真实检索结果，search_evidence 工具调用与返回的证据片段 ID
  均以 "sample_" 前缀标注，并在 claim 的 support_reason 中注明为演示数据。
- 真实检索链路（Day 5）接入后，将替换 _run_sample_evidence_search。

事件协议定义见 docs/architecture.md 「三、流式事件协议」。
"""

import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.llm import default_params, get_async_llm_client, llm_model

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    workspace_id: str
    messages: List[ChatMessage]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sample_evidence_for(query: str) -> Dict[str, Any]:
    """返回明确标注的样例证据，不是真实检索结果。

    真实检索链路见 Day 5 计划（docs/architecture.md、services/retrieval.py 待实现）。
    这里固定返回项目申报案例的样例片段，用于演示折叠证据卡的交互。
    """
    return {
        "tool_name": "search_evidence",
        "arguments": {"query": query, "workspace_id": "sample"},
        "result": {
            "is_sample": True,
            "note": "样例数据，非真实检索结果，用于演示折叠证据卡交互",
            "evidence_spans": [
                {
                    "id": "sample_ev_001",
                    "document_name": "科研项目申报指南2024.pdf（样例）",
                    "page": 2,
                    "text": "重点项目申请人须为副教授及以上职称。",
                    "is_sample": True,
                },
                {
                    "id": "sample_ev_002",
                    "document_name": "科研项目申报指南2024.pdf（样例）",
                    "page": 3,
                    "text": "申报截止时间为2024年11月15日，逾期不予受理。",
                    "is_sample": True,
                },
            ],
        },
    }


def _sample_claim(evidence_result: Dict[str, Any]) -> Dict[str, Any]:
    span_ids = [span["id"] for span in evidence_result["evidence_spans"]]
    return {
        "id": f"sample_claim_{uuid.uuid4().hex[:8]}",
        "text": "以下为样例证据摘录，用于演示折叠来源卡交互，并非针对本次提问的真实检索结果。",
        "evidence_span_ids": span_ids,
        "validation_status": "pending",
        "is_sample": True,
    }


async def _stream_chat(req: ChatStreamRequest, request: Request) -> AsyncIterator[str]:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    model = llm_model()

    yield _sse(
        "run_started",
        {"type": "run_started", "run_id": run_id, "model": model, "timestamp": _now_iso()},
    )

    claims_count = 0
    evidence_count = 0

    try:
        client = get_async_llm_client()
        params = default_params()
        messages = [{"role": m.role, "content": m.content} for m in req.messages]

        stream = await client.chat.completions.create(
            model=model, messages=messages, stream=True, **params
        )

        last_user_message = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), ""
        )

        try:
            async for chunk in stream:
                if await request.is_disconnected():
                    break

                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield _sse(
                        "text_delta",
                        {"type": "text_delta", "delta": delta, "timestamp": _now_iso()},
                    )
        finally:
            await stream.close()

        if await request.is_disconnected():
            return

        # Day 2：真实检索链路尚未接入，用明确标注的样例证据展示折叠证据卡。
        tool_call = _sample_evidence_for(last_user_message)
        yield _sse(
            "tool_started",
            {
                "type": "tool_started",
                "tool_name": tool_call["tool_name"],
                "arguments": tool_call["arguments"],
                "timestamp": _now_iso(),
            },
        )
        yield _sse(
            "tool_finished",
            {
                "type": "tool_finished",
                "tool_name": tool_call["tool_name"],
                "result": tool_call["result"],
                "duration_ms": 1,
                "timestamp": _now_iso(),
            },
        )
        evidence_count = len(tool_call["result"]["evidence_spans"])

        claim = _sample_claim(tool_call["result"])
        claims_count = 1
        yield _sse(
            "claim_ready",
            {"type": "claim_ready", "claim": claim, "timestamp": _now_iso()},
        )

        yield _sse(
            "run_finished",
            {
                "type": "run_finished",
                "run_id": run_id,
                "summary": {
                    "claims_count": claims_count,
                    "evidence_spans_count": evidence_count,
                    "visual_evidences_count": 0,
                    "clarifications_count": 0,
                },
                "timestamp": _now_iso(),
            },
        )

    except Exception as exc:  # noqa: BLE001 — 需要把任意异常转为 error 事件
        yield _sse(
            "error",
            {
                "type": "error",
                "error_code": type(exc).__name__,
                "message": str(exc),
                "recoverable": True,
                "timestamp": _now_iso(),
            },
        )


@router.post("/stream")
async def chat_stream(req: ChatStreamRequest, request: Request) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat(req, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
