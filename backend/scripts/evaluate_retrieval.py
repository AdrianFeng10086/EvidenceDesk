"""在开发集上评测 Case 级检索：向量基线 vs 向量 + BM25 + RRF。

用法（在 backend/ 目录下）：

    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --provider cloudflare --dimension 1024

脚本使用独立临时数据库、上传目录和 Chroma 目录，不会污染开发数据。
输出默认为项目根目录 `data/eval/day5-dev-recall.json`。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

GROUND_TRUTH = PROJECT_ROOT / "data" / "eval" / "dev_retrieval_ground_truth.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "eval" / "day5-dev-recall.json"
K = 5


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _matches(text: str, terms: List[str]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(term) in normalized for term in terms)


def _wait_ready(client, version_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/api/documents/{version_id}/status")
        response.raise_for_status()
        last = response.json()["version"]
        if last["parse_status"] == "failed":
            raise RuntimeError(f"解析失败：{last}")
        if last["parse_status"] == "success" and last["index_status"] == "ready":
            return last
        time.sleep(0.05)
    raise RuntimeError(f"等待索引超时：{last}")


def _first_hit_rank(texts: List[str], terms: List[str]) -> int:
    for index, text in enumerate(texts, start=1):
        if _matches(text, terms):
            return index
    return 0


def _rate(values: List[int], k: int) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if 0 < value <= k) / len(values)


def _mrr(values: List[int]) -> float:
    if not values:
        return 0.0
    return sum((1.0 / value) if value > 0 else 0.0 for value in values) / len(values)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="evidence-desk-eval-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{(temp_root / 'eval.db').as_posix()}"
    os.environ["DATA_DIR"] = str(temp_root / "data")
    os.environ["UPLOAD_DIR"] = str(temp_root / "uploads")
    os.environ["CHROMA_PERSIST_DIR"] = str(temp_root / "chroma")
    os.environ["CHROMA_EVIDENCE_COLLECTION"] = "evidence_chunks_eval"
    os.environ["EMBEDDING_PROVIDER"] = args.provider
    os.environ["EMBEDDING_MODEL"] = args.model
    os.environ["EMBEDDING_DIMENSION"] = str(args.dimension)
    os.environ["DEMO_MODE"] = "true"
    os.environ["DEMO_WORKSPACE_ID"] = "eval_workspace"
    os.environ["DEMO_USER_ID"] = "eval_user"
    os.environ["RETRIEVAL_TOP_K"] = str(K)
    os.environ["INDEX_BACKFILL_ON_STARTUP"] = "false"

    from fastapi.testclient import TestClient

    import main
    from core.config import get_settings
    from core.database import SessionLocal
    from db.models import RetrievalChunk
    from services import vector_store
    from services.index_config import get_index_config

    ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    settings = get_settings()
    config = get_index_config()

    question_records: List[Dict[str, Any]] = []
    per_example: Dict[str, Any] = {}

    with TestClient(main.app) as client:
        for example_key, example in ground_truth["examples"].items():
            workspace_response = client.post(
                "/api/workspaces", json={"name": f"评测-{example_key}"}
            )
            workspace_response.raise_for_status()
            workspace_id = workspace_response.json()["id"]

            scope_items = []
            for relative_path in example["documents"]:
                path = PROJECT_ROOT / relative_path
                with path.open("rb") as source:
                    upload = client.post(
                        f"/api/workspaces/{workspace_id}/documents",
                        files={"file": (path.name, source, "text/plain")},
                    )
                upload.raise_for_status()
                payload = upload.json()
                version = _wait_ready(client, payload["version"]["id"])
                scope_items.append(
                    {
                        "workspace_id": workspace_id,
                        "document_version_id": version["id"],
                    }
                )

            case_response = client.post(
                "/api/cases",
                json={"title": f"评测-{example_key}", "scope_items": scope_items},
            )
            case_response.raise_for_status()
            case_id = case_response.json()["id"]

            fused_ranks: List[int] = []
            vector_ranks: List[int] = []
            for question in example["questions"]:
                response = client.post(
                    f"/api/cases/{case_id}/retrieve",
                    json={"query": question["question"], "top_k": K},
                )
                response.raise_for_status()
                body = response.json()
                terms = question["expected_terms"]

                texts = [result.get("text", "") for result in body["results"]]
                fused_rank = _first_hit_rank(texts, terms)
                fused_ranks.append(fused_rank)

                baseline_ids = [
                    item["chunk_id"]
                    for item in body["diagnostics"].get("vector_baseline", [])[:K]
                ]
                chunk_texts: List[str] = []
                with SessionLocal() as db:
                    for chunk_id in baseline_ids:
                        chunk = db.get(RetrievalChunk, chunk_id)
                        chunk_texts.append(chunk.text if chunk else "")
                vector_rank = _first_hit_rank(chunk_texts, terms)
                vector_ranks.append(vector_rank)

                question_records.append(
                    {
                        "example": example_key,
                        "id": question["id"],
                        "question": question["question"],
                        "expected_terms": terms,
                        "status": body["status"],
                        "empty_reason": body["empty_reason"],
                        "fused_hit_rank": fused_rank,
                        "vector_baseline_hit_rank": vector_rank,
                        "top_k": [
                            {
                                "chunk_id": result["chunk_id"],
                                "evidence_span_id": result["evidence_span_id"],
                                "source_label": result["source_label"],
                                "page": result["page"],
                                "text": result["text"][:240],
                                "scores": result["scores"],
                            }
                            for result in body["results"]
                        ],
                    }
                )

            per_example[example_key] = {
                "question_count": len(example["questions"]),
                "fused_hit_at_1": _rate(fused_ranks, 1),
                "fused_hit_at_5": _rate(fused_ranks, K),
                "fused_mrr": _mrr(fused_ranks),
                "vector_hit_at_1": _rate(vector_ranks, 1),
                "vector_hit_at_5": _rate(vector_ranks, K),
                "vector_mrr": _mrr(vector_ranks),
            }

    all_fused = [record["fused_hit_rank"] for record in question_records]
    all_vector = [record["vector_baseline_hit_rank"] for record in question_records]
    empty_reasons: Dict[str, int] = {}
    for record in question_records:
        reason = record["empty_reason"] or "OK"
        empty_reasons[reason] = empty_reasons.get(reason, 0) + 1

    record = {
        "dataset": ground_truth["version"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "k": K,
        "config": config.to_dict(),
        "runtime": {
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "embedding_dimension": settings.embedding_dimension,
            "chroma_collection": vector_store.collection_name(config.index_version),
        },
        "summary": {
            "question_count": len(question_records),
            "fused_hit_at_1": _rate(all_fused, 1),
            "fused_hit_at_5": _rate(all_fused, K),
            "fused_mrr": _mrr(all_fused),
            "vector_hit_at_1": _rate(all_vector, 1),
            "vector_hit_at_5": _rate(all_vector, K),
            "vector_mrr": _mrr(all_vector),
            "empty_reason_counts": empty_reasons,
        },
        "per_example": per_example,
        "questions": question_records,
    }
    return record


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="开发集检索召回评测")
    parser.add_argument(
        "--provider",
        default="local",
        help="嵌入提供方（local/cloudflare，默认 local，离线可复现）",
    )
    parser.add_argument(
        "--model",
        default="local-hash-v1",
        help="嵌入模型名；cloudflare 时可用 @cf/qwen/qwen3-embedding-0.6b",
    )
    parser.add_argument("--dimension", type=int, default=256)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    if args.provider == "cloudflare":
        if args.model == "local-hash-v1":
            args.model = "@cf/qwen/qwen3-embedding-0.6b"
        if args.dimension == 256:
            args.dimension = 1024

    record = run(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = record["summary"]
    print(f"开发集问题数: {summary['question_count']}")
    print(
        f"融合检索 Hit@1={summary['fused_hit_at_1']:.3f} "
        f"Hit@5={summary['fused_hit_at_5']:.3f} MRR={summary['fused_mrr']:.3f}"
    )
    print(
        f"向量基线   Hit@1={summary['vector_hit_at_1']:.3f} "
        f"Hit@5={summary['vector_hit_at_5']:.3f} MRR={summary['vector_mrr']:.3f}"
    )
    print(f"空结果原因: {summary['empty_reason_counts']}")
    print(f"记录已写入: {output}")


if __name__ == "__main__":
    main_cli()
