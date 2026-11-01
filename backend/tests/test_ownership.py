"""资料空间与访问主体绑定。"""

from __future__ import annotations

from tests.conftest import DEMO_WORKSPACE_ID
from tests.helpers import upload_text


def test_workspace_records_owner(client):
    response = client.post("/api/workspaces", json={"name": "我的资料空间"})
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["owner_id"] == "demo_user"


def test_other_principal_cannot_read_or_upload_to_workspace(
    client, workspace_id, intruder_headers
):
    get_response = client.get(
        f"/api/workspaces/{workspace_id}/documents", headers=intruder_headers
    )
    assert get_response.status_code == 403, get_response.text
    assert get_response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"

    denied = upload_text(
        client,
        workspace_id,
        "越权.txt",
        "不应写入",
        media_type="text/plain",
        headers=intruder_headers,
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


def test_other_principal_cannot_read_document_content(
    client, workspace_id, intruder_headers
):
    uploaded = upload_text(client, workspace_id, "制度.txt", "内容\n")
    assert uploaded.status_code == 201
    version_id = uploaded.json()["version"]["id"]

    detail = client.get(f"/api/documents/{version_id}", headers=intruder_headers)
    assert detail.status_code == 403
    content = client.get(
        f"/api/documents/{version_id}/content", headers=intruder_headers
    )
    assert content.status_code == 403
    original = client.get(
        f"/api/documents/{version_id}/original", headers=intruder_headers
    )
    assert original.status_code == 403


def test_workspace_list_is_scoped_to_principal(client, intruder_headers):
    demo_list = client.get("/api/workspaces")
    assert demo_list.status_code == 200
    demo_ids = {workspace["id"] for workspace in demo_list.json()}
    assert DEMO_WORKSPACE_ID in demo_ids

    intruder_list = client.get("/api/workspaces", headers=intruder_headers)
    assert intruder_list.status_code == 200
    assert intruder_list.json() == []

    created = client.post(
        "/api/workspaces",
        json={"name": "访客空间"},
        headers=intruder_headers,
    )
    assert created.status_code == 201
    assert created.json()["owner_id"] == "intruder"
    assert created.json()["id"] not in demo_ids


def test_chat_stream_requires_workspace_ownership(client, intruder_headers):
    response = client.post(
        "/api/chat/stream",
        json={
            "workspace_id": DEMO_WORKSPACE_ID,
            "messages": [{"role": "user", "content": "你好"}],
        },
        headers=intruder_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
