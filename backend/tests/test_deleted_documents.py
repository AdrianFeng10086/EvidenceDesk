"""原始文件被删除后，数据库里的旧记录不再指向已删除的文档。"""

from __future__ import annotations

from pathlib import Path

from core.config import get_settings
from tests.helpers import upload_text


def _original_path(workspace_id: str, payload: dict) -> Path:
    version = payload["version"]
    document = payload["document"]
    return (
        get_settings().upload_dir
        / "workspaces"
        / workspace_id
        / "documents"
        / document["id"]
        / "versions"
        / version["id"]
        / f"original{version['file_suffix']}"
    )


def test_deleted_original_is_hidden_from_list_and_search(client, workspace_id):
    upload = upload_text(
        client,
        workspace_id,
        "将被删除.txt",
        "需要删除的条款：这条证据不应该再被检索到。\n",
    )
    assert upload.status_code == 201, upload.text
    payload = upload.json()
    version_id = payload["version"]["id"]

    original = _original_path(workspace_id, payload)
    assert original.is_file()
    original.unlink()

    detail = client.get(f"/api/documents/{version_id}")
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "ORIGINAL_FILE_MISSING"

    documents = client.get(f"/api/workspaces/{workspace_id}/documents")
    assert documents.status_code == 200
    assert documents.json()["documents"] == []

    search = client.get(
        f"/api/workspaces/{workspace_id}/evidence/search",
        params={"q": "删除的条款"},
    )
    assert search.status_code == 200
    assert search.json()["evidence_spans"] == []
