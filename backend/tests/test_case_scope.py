"""Case 范围项：固定引用跨资料空间的文档版本。"""

from __future__ import annotations

from core.database import SessionLocal
from db.models import Case, RetrievalScopeItem, Workspace, utcnow
from tests.helpers import upload_text


def _create_workspace(client, name: str) -> str:
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_case_scope_can_reference_versions_from_two_workspaces(client, workspace_id):
    other_workspace = _create_workspace(client, "第二个资料空间")

    first = upload_text(client, workspace_id, "指南A.txt", "第一份空间的证据。\n")
    second = upload_text(client, other_workspace, "指南B.txt", "第二份空间的证据。\n")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    with SessionLocal() as db:
        case = Case(
            owner_id="demo_user",
            title="跨空间核对事项",
            primary_workspace_id=workspace_id,
        )
        db.add(case)
        db.flush()
        db.add(
            RetrievalScopeItem(
                case_id=case.id,
                workspace_id=workspace_id,
                document_version_id=first.json()["version"]["id"],
            )
        )
        db.add(
            RetrievalScopeItem(
                case_id=case.id,
                workspace_id=other_workspace,
                document_version_id=second.json()["version"]["id"],
            )
        )
        db.commit()

        items = db.query(RetrievalScopeItem).filter_by(case_id=case.id).all()
        assert len(items) == 2
        assert {item.workspace_id for item in items} == {workspace_id, other_workspace}


def test_deleted_workspace_blocks_document_access(client, workspace_id):
    upload = upload_text(client, workspace_id, "空间删除.txt", "空间删除后的证据。\n")
    assert upload.status_code == 201, upload.text
    version_id = upload.json()["version"]["id"]

    with SessionLocal() as db:
        workspace = db.get(Workspace, workspace_id)
        assert workspace is not None
        workspace.deleted_at = utcnow()
        workspace.deleted_by = "demo_user"
        db.commit()

    documents = client.get(f"/api/workspaces/{workspace_id}/documents")
    assert documents.status_code == 404
    assert documents.json()["error"]["code"] == "WORKSPACE_DELETED"

    detail = client.get(f"/api/documents/{version_id}")
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "WORKSPACE_DELETED"
