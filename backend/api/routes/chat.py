"""
对话流式接口 (SSE)

Day 2 范围：
- 真实模型文本流（text_delta）接入 DeepSeek（OpenAI 兼容接口）
- search_evidence 工具调用返回资料空间中真实存在的 EvidenceSpan
  （首版为确定性关键词召回，Day 5 会替换为向量 + BM25）
- 证据片段带文档版本、页码、字符范围与文字框，前端据此跳转和高亮

事件协议定义见 docs/architecture.md 「三、流式事件协议」。
"""

import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import SessionLocal, get_db
from services.access import (
    Principal,
    get_principal,
    require_case_access,
    require_workspace_access,
)
from services.evidence_search import search_workspace_evidence
from services.llm import default_params, get_async_llm_client, llm_model
from services.retrieval import retrieve_evidence

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    workspace_id: str
    # 提供 case_id 时使用 Case 固定范围检索；否则保留空间级关键词召回
    case_id: Optional[str] = None
    messages: List[ChatMessage]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _search_evidence(
    workspace_id: str,
    query: str,
    *,
    case_id: Optional[str],
    principal: Principal,
) -> Dict[str, Any]:
    """返回真实证据片段。

    有 case_id 时走 Case 固定范围检索（可跨空间）；否则保留空间级关键词
    召回以兼容现有前端。使用独立短会话，避免绑定长时间运行的 SSE 连接。
    """
    if case_id:
        with SessionLocal() as db:
            retrieval = retrieve_evidence(
                db,
                case_id=case_id,
                principal=principal,
                query=query,
                top_k=5,
                record_run=True,
            )
        return {
            "tool_name": "retrieve_evidence",
            "arguments": {"query": query, "case_id": case_id},
            "result": {
                "is_sample": False,
                "note": retrieval["note"],
                "status": retrieval["status"],
                "empty_reason": retrieval["empty_reason"],
                "retrieval_log_id": retrieval["retrieval_log_id"],
                "run_id": retrieval["run_id"],
                "evidence_spans": retrieval["results"],
            },
        }

    with SessionLocal() as db:
        spans = search_workspace_evidence(db, workspace_id, query, limit=5)

    return {
        "tool_name": "search_evidence",
        "arguments": {"query": query, "workspace_id": workspace_id},
        "result": {
            "is_sample": False,
            "note": None if spans else "资料空间中没有匹配的已解析证据片段",
            "evidence_spans": spans,
        },
    }


def _evidence_claim(evidence_result: Dict[str, Any]) -> Dict[str, Any]:
    spans = evidence_result["evidence_spans"]
    if spans:
        text = f"以上结论引用了 {len(spans)} 处原文证据片段，点击证据卡可定位到原文。"
    else:
        text = "本次没有检索到可引用的原文证据片段。"
    return {
        "id": f"claim_{uuid.uuid4().hex[:8]}",
        "text": text,
        "evidence_span_ids": [span["id"] for span in spans],
        "validation_status": "pending",
        "is_sample": False,
    }


async def _stream_chat(
    req: ChatStreamRequest, request: Request, principal: Principal
) -> AsyncIterator[str]:
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

        # 首版关键词召回：返回真实 EvidenceSpan（含版本、坐标与上下文）。
        tool_call = _search_evidence(
            req.workspace_id,
            last_user_message,
            case_id=req.case_id,
            principal=principal,
        )
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

        claim = _evidence_claim(tool_call["result"])
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
async def chat_stream(
    req: ChatStreamRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> StreamingResponse:
    # 所有权校验入口：即使首版只有演示账户，也不允许跨资料空间提问
    require_workspace_access(db, req.workspace_id, principal)
    if req.case_id:
        require_case_access(db, req.case_id, principal)

    return StreamingResponse(
        _stream_chat(req, request, principal),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
