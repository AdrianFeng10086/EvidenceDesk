"""Case 级检索：范围、跨空间隔离、过滤、空结果原因、删除与过期。"""

from __future__ import annotations

import time

from core.database import SessionLocal
from db.models import DocumentVersion
from tests.helpers import upload_text


def _create_workspace(client, name: str) -> str:
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _wait_version_ready(client, version_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        response = client.get(f"/api/documents/{version_id}/status")
        assert response.status_code == 200, response.text
        last = response.json()["version"]
        if last["parse_status"] == "failed":
            raise AssertionError(f"解析失败：{last}")
        if last["parse_status"] == "success" and last["index_status"] == "ready":
            return last
        time.sleep(0.02)
    raise AssertionError(f"等待索引超时：{last}")


def _upload(client, workspace_id: str, filename: str, content: str):
    response = upload_text(client, workspace_id, filename, content)
    assert response.status_code == 201, response.text
    payload = response.json()
    payload["version"] = _wait_version_ready(client, payload["version"]["id"])
    return payload


def _case(client, title: str, items: list[dict]) -> dict:
    response = client.post(
        "/api/cases",
        json={"title": title, "scope_items": items},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_scope(client, case_id: str, workspace_id: str, version_id: str):
    return client.post(
        f"/api/cases/{case_id}/scope",
        json={"workspace_id": workspace_id, "document_version_id": version_id},
    )


def _retrieve(client, case_id: str, query: str, *, top_k: int = 5, filters=None):
    response = client.post(
        f"/api/cases/{case_id}/retrieve",
        json={
            "query": query,
            "top_k": top_k,
            "filters": filters or {},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_known_evidence_enters_top_k_and_maps_to_real_span(client):
    workspace_id = _create_workspace(client, "报销空间")
    content = (
        "第一条：重点项目申请人须为副教授及以上职称。\n\n"
        "第二条：申报截止时间为2024年11月15日，逾期不予受理。\n"
    )
    upload = _upload(client, workspace_id, "申报指南.txt", content)
    case = _case(
        client,
        "截止时间核对",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": upload["version"]["id"],
            }
        ],
    )

    body = _retrieve(client, case["id"], "申报截止时间是什么时候")
    assert body["status"] == "ok", body
    assert body["empty_reason"] is None
    top = body["results"][0]
    assert "截止时间" in top["text"]
    assert top["document_version_id"] == upload["version"]["id"]
    assert top["workspace_id"] == workspace_id
    assert content[top["char_start"] : top["char_end"]] == top["text"]
    assert top["chunk_id"].startswith("chk_")
    assert top["evidence_span_id"] == top["id"]
    assert body["run_id"] and body["retrieval_log_id"]
    assert body["scope_snapshot"]["counts"]["scope_items"] == 1
    assert body["scope_snapshot"]["items"][0]["source_state"] == "active"
    assert body["scope_hash"]
    assert body["diagnostics"]["fusion"] == "rrf"
    assert body["diagnostics"]["vector_baseline"]
    assert body["diagnostics"]["index_version"] == body["index_status"]["index_version"]


def test_two_workspaces_with_same_named_files_do_not_cross(client):
    workspace_a = _create_workspace(client, "甲空间")
    workspace_b = _create_workspace(client, "乙空间")
    content_a = "住宿费标准：普通员工每晚不超过 400 元。\n\n交通费实报实销。\n"
    content_b = "住宿费标准：经理级每晚不超过 600 元。\n\n电池保修期为 6 个月。\n"
    upload_a = _upload(client, workspace_a, "同名规则.txt", content_a)
    upload_b = _upload(client, workspace_b, "同名规则.txt", content_b)

    case = _case(
        client,
        "跨空间住宿标准",
        [
            {
                "workspace_id": workspace_a,
                "document_version_id": upload_a["version"]["id"],
            },
            {
                "workspace_id": workspace_b,
                "document_version_id": upload_b["version"]["id"],
            },
        ],
    )
    assert case["scope_item_count"] == 2

    body = _retrieve(client, case["id"], "普通员工住宿费每晚上限是多少", top_k=5)
    assert body["status"] == "ok", body
    top = body["results"][0]
    assert "400" in top["text"]
    assert top["workspace_id"] == workspace_a
    assert top["workspace_name"] == "甲空间"
    assert top["file_name"] == "同名规则.txt"

    body_b = _retrieve(client, case["id"], "经理级住宿费每晚上限是多少", top_k=5)
    top_b = body_b["results"][0]
    assert "600" in top_b["text"]
    assert top_b["workspace_id"] == workspace_b
    assert top_b["workspace_name"] == "乙空间"

    # 同一问题可以同时返回两个空间的同名文件，来源必须可区分
    mixed = _retrieve(client, case["id"], "住宿费标准", top_k=5)
    labels = {result["source_label"] for result in mixed["results"]}
    assert any("甲空间" in label for label in labels)
    assert any("乙空间" in label for label in labels)


def test_filters_by_workspace_version_type_scope_and_deletion_state(client):
    workspace_a = _create_workspace(client, "过滤甲")
    workspace_b = _create_workspace(client, "过滤乙")

    response = upload_text(
        client,
        workspace_a,
        "报销2024.md",
        "# 住宿标准\n\n普通员工住宿费每晚不超过 400 元。\n",
    )
    assert response.status_code == 201, response.text
    upload_a = response.json()
    _wait_version_ready(client, upload_a["version"]["id"])
    upload_b = _upload(
        client, workspace_b, "报销2023.txt", "普通员工住宿费每晚不超过 500 元。\n"
    )

    # 为版本补充适用范围
    with SessionLocal() as db:
        version = db.get(DocumentVersion, upload_a["version"]["id"])
        version.applicable_scope = "2024年度"
        db.commit()

    case = _case(
        client,
        "过滤事项",
        [
            {
                "workspace_id": workspace_a,
                "document_version_id": upload_a["version"]["id"],
            },
            {
                "workspace_id": workspace_b,
                "document_version_id": upload_b["version"]["id"],
            },
        ],
    )

    by_workspace = _retrieve(
        client,
        case["id"],
        "住宿费标准",
        filters={"workspace_ids": [workspace_b]},
    )
    assert {result["workspace_id"] for result in by_workspace["results"]} == {
        workspace_b
    }

    by_version = _retrieve(
        client,
        case["id"],
        "住宿费标准",
        filters={"document_version_ids": [upload_a["version"]["id"]]},
    )
    assert {result["document_version_id"] for result in by_version["results"]} == {
        upload_a["version"]["id"]
    }

    by_type = _retrieve(
        client,
        case["id"],
        "住宿费标准",
        filters={"file_suffixes": [".txt"]},
    )
    assert {result["file_suffix"] for result in by_type["results"]} == {".txt"}

    by_scope = _retrieve(
        client,
        case["id"],
        "住宿费标准",
        filters={"applicable_scopes": ["2024年度"]},
    )
    assert {result["document_version_id"] for result in by_scope["results"]} == {
        upload_a["version"]["id"]
    }

    by_chunk_type = _retrieve(
        client,
        case["id"],
        "住宿标准",
        filters={"chunk_types": ["heading"]},
    )
    assert by_chunk_type["results"]
    assert {result["chunk_type"] for result in by_chunk_type["results"]} == {
        "heading"
    }


def test_empty_result_reasons_are_distinguishable(client, workspace_id):
    no_scope = client.post("/api/cases", json={"title": "空范围"})
    assert no_scope.status_code == 201, no_scope.text
    body = _retrieve(client, no_scope.json()["id"], "任何问题")
    assert body["status"] == "empty"
    assert body["empty_reason"] == "NO_SCOPE"

    upload = _upload(client, workspace_id, "索引未就绪.txt", "截止时间为11月15日。\n")
    with SessionLocal() as db:
        version = db.get(DocumentVersion, upload["version"]["id"])
        version.index_status = "pending"
        db.commit()
    case = _case(
        client,
        "索引事项",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": upload["version"]["id"],
            }
        ],
    )
    body = _retrieve(client, case["id"], "截止时间")
    assert body["empty_reason"] == "INDEX_NOT_READY", body

    # 恢复索引后可以检索
    with SessionLocal() as db:
        version = db.get(DocumentVersion, upload["version"]["id"])
        version.index_status = "ready"
        db.commit()
    body = _retrieve(client, case["id"], "截止时间")
    assert body["status"] == "ok", body

    no_match = _retrieve(client, case["id"], "zzzzqqqq")
    assert no_match["status"] == "empty"
    assert no_match["empty_reason"] == "NO_MATCH"

    filtered = _retrieve(
        client,
        case["id"],
        "截止时间",
        filters={"applicable_scopes": ["不存在的年度"]},
    )
    assert filtered["empty_reason"] == "FILTERED_OUT"

    # 删除后，新检索不能继续使用该来源
    deleted = client.delete(
        f"/api/workspaces/{workspace_id}/documents/{upload['document']['id']}"
    )
    assert deleted.status_code == 200, deleted.text
    after_delete = _retrieve(client, case["id"], "截止时间")
    assert after_delete["status"] == "empty"
    assert after_delete["empty_reason"] == "ALL_SOURCES_DELETED"


def test_retrieval_rejects_out_of_scope_and_unauthorized_access(
    client, workspace_id, intruder_headers
):
    upload = _upload(client, workspace_id, "范围校验.txt", "审批上限为500元。\n")
    case = _case(
        client,
        "范围校验事项",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": upload["version"]["id"],
            }
        ],
    )

    denied = client.post(
        f"/api/cases/{case['id']}/retrieve",
        json={"query": "审批上限"},
        headers=intruder_headers,
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "CASE_FORBIDDEN"

    # 其他所有者的空间不能加入范围
    intruder_workspace = client.post(
        "/api/workspaces", json={"name": "入侵者空间"}, headers=intruder_headers
    ).json()["id"]
    intruder_upload = upload_text(
        client,
        intruder_workspace,
        "入侵.txt",
        "不应被引用。\n",
        headers=intruder_headers,
    )
    assert intruder_upload.status_code == 201, intruder_upload.text
    add = _add_scope(
        client,
        case["id"],
        intruder_workspace,
        intruder_upload.json()["version"]["id"],
    )
    assert add.status_code == 403, add.text
    assert add.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"

    # 过滤条件不能指向 Case 范围外的版本
    other_upload = _upload(client, workspace_id, "另外一个.txt", "另一个文档。\n")
    out_of_scope = client.post(
        f"/api/cases/{case['id']}/retrieve",
        json={
            "query": "审批上限",
            "filters": {"document_version_ids": [other_upload["version"]["id"]]},
        },
    )
    assert out_of_scope.status_code == 403, out_of_scope.text
    assert out_of_scope.json()["error"]["code"] == "VERSION_OUT_OF_SCOPE"


def test_deleted_source_is_excluded_and_historical_log_is_marked(client, workspace_id):
    content = "发票时间：需在费用发生后 30 天内提交。\n"
    upload = _upload(client, workspace_id, "票据要求.txt", content)
    case = _case(
        client,
        "历史日志事项",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": upload["version"]["id"],
            }
        ],
    )

    before = _retrieve(client, case["id"], "发票需要多久内提交")
    assert before["status"] == "ok", before
    log_id = before["retrieval_log_id"]

    deleted = client.delete(
        f"/api/workspaces/{workspace_id}/documents/{upload['document']['id']}"
    )
    assert deleted.status_code == 200, deleted.text

    after = _retrieve(client, case["id"], "发票需要多久内提交")
    assert after["status"] == "empty"
    assert after["empty_reason"] == "ALL_SOURCES_DELETED"

    log = client.get(f"/api/retrieval/logs/{log_id}")
    assert log.status_code == 200, log.text
    body = log.json()
    assert body["result_count"] >= 1
    assert body["results"][0]["source_status"] == "document_deleted"
    assert body["results"][0]["source_available"] is False
    assert body["historical_notice"]


def test_delete_one_of_two_sources_keeps_other_searchable(client, workspace_id):
    first = _upload(client, workspace_id, "保留来源.txt", "保留条款：保修期为一年。\n")
    second = _upload(client, workspace_id, "删除来源.txt", "删除条款：保修期为两年。\n")
    case = _case(
        client,
        "部分删除事项",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": first["version"]["id"],
            },
            {
                "workspace_id": workspace_id,
                "document_version_id": second["version"]["id"],
            },
        ],
    )

    deleted = client.delete(
        f"/api/workspaces/{workspace_id}/documents/{second['document']['id']}"
    )
    assert deleted.status_code == 200, deleted.text

    body = _retrieve(client, case["id"], "保修期")
    assert body["status"] == "ok", body
    assert body["counts"]["deleted_sources"] == 1
    assert {result["document_version_id"] for result in body["results"]} == {
        first["version"]["id"]
    }
    assert all("两年" not in result["text"] for result in body["results"])

    # 明确只查已删除来源时也不会把删除内容重新放进候选
    deleted_only = _retrieve(
        client,
        case["id"],
        "保修期",
        filters={"deletion_status": "deleted"},
    )
    assert deleted_only["status"] == "empty"
    assert deleted_only["empty_reason"] == "ALL_SOURCES_DELETED"


def test_scope_change_marks_old_runs_stale(client, workspace_id):
    first = _upload(client, workspace_id, "第一份.txt", "第一条：截止时间为11月15日。\n")
    second = _upload(client, workspace_id, "第二份.txt", "第二条：材料一式三份。\n")
    case = _case(
        client,
        "范围变更事项",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": first["version"]["id"],
            }
        ],
    )

    before = _retrieve(client, case["id"], "截止时间")
    run_id = before["run_id"]
    runs = client.get(f"/api/cases/{case['id']}/runs").json()["runs"]
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["stale"] is False

    added = _add_scope(
        client, case["id"], workspace_id, second["version"]["id"]
    )
    assert added.status_code == 201, added.text

    runs = client.get(f"/api/cases/{case['id']}/runs").json()["runs"]
    old_run = next(run for run in runs if run["id"] == run_id)
    assert old_run["status"] == "stale"
    assert old_run["stale_reason"] == "scope_changed"
    assert old_run["stale_at"]

    after = _retrieve(client, case["id"], "截止时间")
    assert after["run_id"] != run_id
    new_runs = client.get(f"/api/cases/{case['id']}/runs").json()["runs"]
    new_run = next(run for run in new_runs if run["id"] == after["run_id"])
    assert new_run["status"] == "succeeded"


def test_stable_chunk_and_span_ids_survive_reindex(client, workspace_id):
    upload = _upload(client, workspace_id, "稳定ID.txt", "审批流程：部门审核后财务审核。\n")
    case = _case(
        client,
        "稳定 ID 事项",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": upload["version"]["id"],
            }
        ],
    )

    first = _retrieve(client, case["id"], "审批流程")
    second = _retrieve(client, case["id"], "审批流程")
    assert first["results"][0]["chunk_id"] == second["results"][0]["chunk_id"]
    assert (
        first["results"][0]["evidence_span_id"]
        == second["results"][0]["evidence_span_id"]
    )

    rebuild = client.post(
        f"/api/documents/{upload['version']['id']}/index/rebuild"
    )
    assert rebuild.status_code == 202, rebuild.text
    deadline = time.time() + 5
    while time.time() < deadline:
        status = client.get(
            f"/api/documents/{upload['version']['id']}/status"
        ).json()["version"]["index_status"]
        if status == "ready":
            break
        time.sleep(0.05)

    third = _retrieve(client, case["id"], "审批流程")
    assert third["results"][0]["chunk_id"] == first["results"][0]["chunk_id"]


def test_case_index_status_and_global_index_status(client, workspace_id):
    upload = _upload(client, workspace_id, "索引状态.txt", "保修期为一年。\n")
    case = _case(
        client,
        "索引状态事项",
        [
            {
                "workspace_id": workspace_id,
                "document_version_id": upload["version"]["id"],
            }
        ],
    )

    status = client.get(f"/api/cases/{case['id']}/retrieval/index-status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["ready_for_retrieval"] is True
    assert body["status_counts"]["ready"] == 1
    assert body["items"][0]["index_version"] == body["config"]["index_version"]

    global_status = client.get("/api/index/status")
    assert global_status.status_code == 200, global_status.text
    global_body = global_status.json()
    assert global_body["version_count"] >= 1
    assert global_body["config"]["tokenizer_version"]
    assert global_body["manifest"]["index_version"] == global_body["config"]["index_version"]
    assert global_body["manifest"]["chunk_count"] >= 1
