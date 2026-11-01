"""损坏、扫描、空白、超限、编码异常等失败状态。"""

from __future__ import annotations

from tests import fixtures
from tests.helpers import upload_bytes, upload_pdf, upload_text


def _detail(client, version_id: str) -> dict:
    response = client.get(f"/api/documents/{version_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_corrupted_pdf_is_recorded_as_failed(client, workspace_id, fixture_dir):
    path = fixtures.make_corrupt_pdf(fixture_dir / "corrupt.pdf")
    response = upload_pdf(client, workspace_id, "损坏文件.pdf", path)
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    detail = _detail(client, version_id)
    version = detail["version"]
    assert version["parse_status"] == "failed"
    assert version["parse_error_code"] == "CORRUPTED"
    assert version["parse_error"]
    assert version["support_level"] == "unsupported"
    assert detail["parse_job"]["status"] == "failed"
    assert detail["pages"] == []


def test_scanned_pdf_without_text_layer_is_explicitly_failed(client, workspace_id, fixture_dir):
    path = fixtures.make_scanned_pdf(fixture_dir / "scanned.pdf", fixture_dir)
    response = upload_pdf(client, workspace_id, "扫描件.pdf", path)
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    version = _detail(client, version_id)["version"]
    assert version["parse_status"] == "failed"
    assert version["parse_error_code"] == "NO_TEXT_LAYER"
    assert "OCR" in version["parse_error"] or "文字层" in version["parse_error"]


def test_blank_pdf_is_recorded_as_empty(client, workspace_id, fixture_dir):
    path = fixtures.make_blank_pdf(fixture_dir / "blank.pdf")
    response = upload_pdf(client, workspace_id, "空白.pdf", path)
    assert response.status_code == 201, response.text

    version = _detail(client, response.json()["version"]["id"])["version"]
    assert version["parse_status"] == "failed"
    assert version["parse_error_code"] == "EMPTY_DOCUMENT"


def test_encrypted_pdf_is_recorded_as_encrypted(client, workspace_id, fixture_dir):
    path = fixtures.make_encrypted_pdf(fixture_dir / "encrypted.pdf", fixture_dir)
    response = upload_pdf(client, workspace_id, "加密.pdf", path)
    assert response.status_code == 201, response.text

    version = _detail(client, response.json()["version"]["id"])["version"]
    assert version["parse_status"] == "failed"
    assert version["parse_error_code"] == "ENCRYPTED"


def test_oversized_text_is_rejected_with_explicit_error(client, workspace_id):
    response = upload_bytes(
        client,
        workspace_id,
        "超大.txt",
        b"a" * (1024 * 1024 + 1024),
        media_type="text/plain",
    )
    assert response.status_code == 413, response.text
    body = response.json()
    assert body["error"]["code"] == "TOO_LARGE"
    assert body["error"]["details"]["max_size_mb"] == 1


def test_unsupported_format_is_rejected(client, workspace_id):
    response = upload_bytes(
        client,
        workspace_id,
        "说明.docx",
        b"PK\x03\x04",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert response.status_code == 415, response.text
    assert response.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_empty_text_file_is_recorded_as_empty(client, workspace_id):
    response = upload_text(client, workspace_id, "空白.txt", "   \n\n\t  \n")
    assert response.status_code == 201, response.text
    version = _detail(client, response.json()["version"]["id"])["version"]
    assert version["parse_status"] == "failed"
    assert version["parse_error_code"] == "EMPTY_DOCUMENT"


def test_binary_text_file_reports_encoding_error(client, workspace_id):
    response = upload_bytes(
        client,
        workspace_id,
        "二进制.txt",
        b"\x00\x01\x02\x03\xff\xfe\x00\x00",
        media_type="text/plain",
    )
    assert response.status_code == 201, response.text
    version = _detail(client, response.json()["version"]["id"])["version"]
    assert version["parse_status"] == "failed"
    assert version["parse_error_code"] == "UNSUPPORTED_ENCODING"


def test_retry_creates_new_attempt(client, workspace_id, fixture_dir):
    path = fixtures.make_corrupt_pdf(fixture_dir / "retry-corrupt.pdf")
    response = upload_pdf(client, workspace_id, "重试.pdf", path)
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]
    assert _detail(client, version_id)["version"]["parse_status"] == "failed"

    retry = client.post(f"/api/documents/{version_id}/parse/retry")
    assert retry.status_code == 202, retry.text

    detail = _detail(client, version_id)
    assert detail["version"]["parse_status"] == "failed"
    assert detail["parse_job"]["attempt"] == 2
    assert detail["parse_job"]["status"] == "failed"
