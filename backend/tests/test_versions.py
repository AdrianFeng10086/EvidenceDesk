"""不可变版本：同名文件的新内容不覆盖旧版本与旧证据。"""

from __future__ import annotations

import hashlib

import pytest

from tests import fixtures
from tests.helpers import upload_bytes, upload_pdf


OLD_TEXT = fixtures.localized(
    "旧版本规定：申报截止时间为2024年11月15日。",
    "Old version: the deadline is November 15, 2024.",
)
NEW_TEXT = fixtures.localized(
    "新版本规定：申报截止时间延长至2025年1月10日。",
    "New version: the deadline is extended to January 10, 2025.",
)


def test_new_version_does_not_overwrite_old_evidence(client, workspace_id, fixture_dir):
    v1_path = fixtures.make_text_pdf(fixture_dir / "guide-v1.pdf", [OLD_TEXT])
    first = upload_pdf(client, workspace_id, "申报指南.pdf", v1_path)
    assert first.status_code == 201, first.text
    v1 = first.json()["version"]

    v2_path = fixtures.make_text_pdf(fixture_dir / "guide-v2.pdf", [NEW_TEXT])
    second = upload_pdf(client, workspace_id, "申报指南.pdf", v2_path)
    assert second.status_code == 201, second.text
    second_payload = second.json()
    v2 = second_payload["version"]

    assert v2["version"] == 2
    assert v2["document_id"] == v1["document_id"]
    assert v2["file_hash"] != v1["file_hash"]
    assert second_payload["document"]["version_count"] == 2

    # 旧版本仍可读取，原文与证据没有被新版本覆盖
    old_detail = client.get(f"/api/documents/{v1['id']}")
    assert old_detail.status_code == 200
    old_payload = old_detail.json()
    assert old_payload["version"]["file_hash"] == v1["file_hash"]
    assert old_payload["version"]["parse_status"] == "success"

    old_content = client.get(f"/api/documents/{v1['id']}/content", params={"page": 1})
    assert old_content.status_code == 200
    old_page = old_content.json()
    assert OLD_TEXT in old_page["text"]
    assert NEW_TEXT not in old_page["text"]
    assert old_page["spans"]

    new_content = client.get(f"/api/documents/{v2['id']}/content", params={"page": 1})
    assert new_content.status_code == 200
    new_page = new_content.json()
    assert NEW_TEXT in new_page["text"]
    assert OLD_TEXT not in new_page["text"]

    # 文档列表只出现一个逻辑文档，最新版本指向 v2
    documents = client.get(f"/api/workspaces/{workspace_id}/documents").json()["documents"]
    assert len(documents) == 1
    assert documents[0]["version_count"] == 2
    assert documents[0]["latest_version"]["id"] == v2["id"]
    assert {item["id"] for item in documents[0]["versions"]} == {v1["id"], v2["id"]}


def test_uploading_identical_bytes_is_idempotent(client, workspace_id, fixture_dir):
    path = fixtures.make_text_pdf(fixture_dir / "same.pdf", [OLD_TEXT])
    first = upload_pdf(client, workspace_id, "重复文件.pdf", path)
    assert first.status_code == 201, first.text
    first_version = first.json()["version"]

    second = upload_pdf(client, workspace_id, "重复文件.pdf", path)
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["duplicate"] is True
    assert payload["version"]["id"] == first_version["id"]

    documents = client.get(f"/api/workspaces/{workspace_id}/documents").json()["documents"]
    assert len(documents) == 1
    assert documents[0]["version_count"] == 1


def test_original_file_and_hash_are_preserved(client, workspace_id, fixture_dir):
    path = fixtures.make_single_column_pdf(fixture_dir / "hash-check.pdf")
    data = path.read_bytes()
    expected_hash = hashlib.sha256(data).hexdigest()

    response = upload_pdf(client, workspace_id, "哈希核对.pdf", path)
    assert response.status_code == 201, response.text
    version = response.json()["version"]
    assert version["file_hash"] == expected_hash
    assert version["file_size"] == len(data)

    download = client.get(f"/api/documents/{version['id']}/original")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == expected_hash
    assert download.content == data


def test_filename_path_is_sanitized(client, workspace_id):
    content = b"# hello\n\nworld\n"
    response = upload_bytes(client, workspace_id, "../../evil.md", content, "text/markdown")
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["version"]["file_name"] == "evil.md"
    assert payload["document"]["name"] == "evil.md"


def test_version_content_fields_are_immutable(client, workspace_id, fixture_dir):
    from core.database import SessionLocal
    from db.models import DocumentVersion

    path = fixtures.make_text_pdf(fixture_dir / "immutable.pdf", [OLD_TEXT])
    response = upload_pdf(client, workspace_id, "不可变.pdf", path)
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    with SessionLocal() as db:
        version = db.get(DocumentVersion, version_id)
        assert version is not None
        version.file_hash = "0" * 64
        with pytest.raises(ValueError, match="不可修改"):
            db.commit()
        db.rollback()

    detail = client.get(f"/api/documents/{version_id}").json()
    assert detail["version"]["file_hash"] != "0" * 64
