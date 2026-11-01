from __future__ import annotations

from pathlib import Path


def upload_pdf(
    client, workspace_id: str, filename: str, path: Path, headers=None, **form
):
    with path.open("rb") as source:
        files = {"file": (filename, source, "application/pdf")}
        return client.post(
            f"/api/workspaces/{workspace_id}/documents",
            files=files,
            data=form,
            headers=headers,
        )


def upload_text(
    client,
    workspace_id: str,
    filename: str,
    content: str,
    media_type: str = "text/plain",
    headers=None,
):
    files = {"file": (filename, content.encode("utf-8"), media_type)}
    return client.post(
        f"/api/workspaces/{workspace_id}/documents", files=files, headers=headers
    )


def upload_bytes(
    client,
    workspace_id: str,
    filename: str,
    content: bytes,
    media_type: str = "application/octet-stream",
    headers=None,
):
    files = {"file": (filename, content, media_type)}
    return client.post(
        f"/api/workspaces/{workspace_id}/documents", files=files, headers=headers
    )


def get_only_document(client, workspace_id: str) -> dict:
    response = client.get(f"/api/workspaces/{workspace_id}/documents")
    assert response.status_code == 200, response.text
    documents = response.json()["documents"]
    assert len(documents) == 1, documents
    return documents[0]
