"""文档软删除、恢复、删除影响与同名重传。"""

from __future__ import annotations

from core.database import SessionLocal
from db.models import Case, RetrievalScopeItem, Run
from tests.helpers import upload_text


def _upload(client, workspace_id: str, filename: str = "删除测试.txt", content: str = "第一条：测试条款。\n"):
    response = upload_text(client, workspace_id, filename, content)
    assert response.status_code == 201, response.text
    return response.json()


def _list(client, workspace_id: str, include_deleted: bool = False):
    response = client.get(
        f"/api/workspaces/{workspace_id}/documents",
        params={"include_deleted": str(include_deleted).lower()},
    )
    assert response.status_code == 200, response.text
    return response.json()["documents"]


def test_soft_delete_hides_document_and_blocks_access(client, workspace_id):
    payload = _upload(client, workspace_id)
    document_id = payload["document"]["id"]
    version_id = payload["version"]["id"]

    assert len(_list(client, workspace_id)) == 1

    impact = client.get(
        f"/api/workspaces/{workspace_id}/documents/{document_id}/delete-impact"
    )
    assert impact.status_code == 200, impact.text
    body = impact.json()
    assert body["version_count"] == 1
    assert body["page_count"] == 1
    assert body["span_count"] >= 1
    assert body["referencing_cases"] == []
    assert body["recent_runs"] == []

    deleted = client.delete(f"/api/workspaces/{workspace_id}/documents/{document_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"]

    assert _list(client, workspace_id) == []
    deleted_docs = _list(client, workspace_id, include_deleted=True)
    assert len(deleted_docs) == 1
    assert deleted_docs[0]["deleted_at"]

    for path in (
        f"/api/documents/{version_id}",
        f"/api/documents/{version_id}/content?page=1",
        f"/api/documents/{version_id}/original",
        f"/api/documents/{version_id}/status",
    ):
        response = client.get(path)
        assert response.status_code == 404, (path, response.text)
        assert response.json()["error"]["code"] == "DOCUMENT_DELETED"

    search = client.get(
        f"/api/workspaces/{workspace_id}/evidence/search",
        params={"q": "测试条款"},
    )
    assert search.status_code == 200
    assert search.json()["evidence_spans"] == []

    restored = client.post(
        f"/api/workspaces/{workspace_id}/documents/{document_id}/restore"
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["deleted_at"] is None
    assert len(_list(client, workspace_id)) == 1
    assert client.get(f"/api/documents/{version_id}").status_code == 200


def test_delete_twice_is_conflict(client, workspace_id):
    payload = _upload(client, workspace_id)
    document_id = payload["document"]["id"]

    assert client.delete(
        f"/api/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 200
    second = client.delete(f"/api/workspaces/{workspace_id}/documents/{document_id}")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DOCUMENT_ALREADY_DELETED"


def test_reupload_same_name_after_delete_creates_new_version(client, workspace_id):
    first = _upload(client, workspace_id, "同名文档.txt", "旧内容：第一条。\n")
    document_id = first["document"]["id"]

    assert client.delete(
        f"/api/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 200

    second = upload_text(
        client,
        workspace_id,
        "同名文档.txt",
        "新内容：第二条。\n",
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["duplicate"] is False
    assert body["document"]["id"] == document_id
    assert body["document"]["deleted_at"] is None
    assert body["version"]["version"] == 2
    assert len(_list(client, workspace_id)) == 1


def test_reupload_identical_file_after_delete_restores_document(client, workspace_id):
    content = "完全相同的文件内容。\n"
    first = _upload(client, workspace_id, "相同文件.txt", content)
    document_id = first["document"]["id"]

    assert client.delete(
        f"/api/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 200

    second = upload_text(client, workspace_id, "相同文件.txt", content)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["duplicate"] is True
    assert body["document"]["id"] == document_id
    assert body["document"]["deleted_at"] is None
    assert len(_list(client, workspace_id)) == 1


def test_reupload_identical_file_restores_missing_original(client, workspace_id):
    content = "删除后原始文件也丢失的文档。\n"
    first = _upload(client, workspace_id, "丢失原文.txt", content)
    document_id = first["document"]["id"]
    version_id = first["version"]["id"]
    document = first["document"]
    version = first["version"]

    from core.config import get_settings

    path = (
        get_settings().upload_dir
        / "workspaces"
        / workspace_id
        / "documents"
        / document["id"]
        / "versions"
        / version["id"]
        / f"original{version['file_suffix']}"
    )

    assert client.delete(
        f"/api/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 200
    path.unlink()

    second = upload_text(client, workspace_id, "丢失原文.txt", content)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["duplicate"] is True
    assert body["document"]["id"] == document_id
    assert body["document"]["deleted_at"] is None
    assert path.is_file()
    assert client.get(f"/api/documents/{version_id}").status_code == 200


def test_delete_impact_reports_referencing_cases_and_runs(client, workspace_id):
    payload = _upload(client, workspace_id)
    document_id = payload["document"]["id"]
    version_id = payload["version"]["id"]

    with SessionLocal() as db:
        case = Case(
            owner_id="demo_user",
            title="引用该文档的事项",
            primary_workspace_id=workspace_id,
        )
        db.add(case)
        db.flush()
        db.add(
            RetrievalScopeItem(
                case_id=case.id,
                workspace_id=workspace_id,
                document_version_id=version_id,
            )
        )
        db.add(Run(case_id=case.id, status="succeeded", query="测试"))
        db.commit()

    impact = client.get(
        f"/api/workspaces/{workspace_id}/documents/{document_id}/delete-impact"
    )
    assert impact.status_code == 200, impact.text
    body = impact.json()
    assert [item["title"] for item in body["referencing_cases"]] == ["引用该文档的事项"]
    assert len(body["recent_runs"]) == 1
    assert body["recent_runs"][0]["status"] == "succeeded"


def test_restore_fails_when_original_file_is_missing(client, workspace_id):
    payload = _upload(client, workspace_id)
    document_id = payload["document"]["id"]
    document = payload["document"]
    version = payload["version"]

    from core.config import get_settings

    path = (
        get_settings().upload_dir
        / "workspaces"
        / workspace_id
        / "documents"
        / document["id"]
        / "versions"
        / version["id"]
        / f"original{version['file_suffix']}"
    )
    assert path.is_file()

    assert client.delete(
        f"/api/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 200
    path.unlink()

    restored = client.post(
        f"/api/workspaces/{workspace_id}/documents/{document_id}/restore"
    )
    assert restored.status_code == 409
    assert restored.json()["error"]["code"] == "ORIGINAL_FILE_MISSING"
