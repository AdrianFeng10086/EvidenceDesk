"""真实 EvidenceSpan 检索：返回版本、页码、字符范围与上下文。"""

from __future__ import annotations

from tests.helpers import upload_text


def _search(client, workspace_id: str, query: str) -> dict:
    response = client.get(
        f"/api/workspaces/{workspace_id}/evidence/search",
        params={"q": query},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_search_returns_real_spans_with_version_and_range(client, workspace_id):
    content = (
        "第一条：重点项目申请人须为副教授及以上职称。\n\n"
        "第二条：申报截止时间为2024年11月15日，逾期不予受理。\n"
    )
    upload = upload_text(client, workspace_id, "申报指南.txt", content)
    assert upload.status_code == 201, upload.text
    version_id = upload.json()["version"]["id"]

    body = _search(client, workspace_id, "截止时间是什么")
    assert body["is_sample"] is False
    assert body["evidence_spans"], body

    span = body["evidence_spans"][0]
    assert span["document_version_id"] == version_id
    assert span["file_name"] == "申报指南.txt"
    assert span["file_suffix"] == ".txt"
    assert span["page"] == 1
    assert span["page_count"] == 1
    assert span["support_level"] == "full"
    assert span["bboxes"] == []
    assert content[span["char_start"] : span["char_end"]] == span["text"]
    assert "截止时间" in span["text"]
    assert span["context_before"]


def test_search_is_scoped_to_workspace(client, workspace_id):
    upload = upload_text(
        client,
        workspace_id,
        "报销制度.txt",
        "单笔超过5000元需部门负责人审批。\n",
    )
    assert upload.status_code == 201, upload.text

    other = client.post("/api/workspaces", json={"name": "另一个资料空间"})
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]

    assert _search(client, workspace_id, "部门负责人审批")["evidence_spans"]
    assert _search(client, other_id, "部门负责人审批")["evidence_spans"] == []


def test_search_without_match_returns_explicit_empty_note(client, workspace_id):
    upload = upload_text(client, workspace_id, "说明.txt", "这一页只讲设备保修。\n")
    assert upload.status_code == 201, upload.text

    body = _search(client, workspace_id, "量子纠缠")
    assert body["evidence_spans"] == []
    assert body["note"]
