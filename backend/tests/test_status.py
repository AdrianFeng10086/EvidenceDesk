"""解析任务状态机：uploaded -> parsing -> indexing -> success。"""

from __future__ import annotations

from tests import fixtures
from tests.helpers import upload_pdf


def test_status_moves_through_parsing_and_indexing(
    client, workspace_id, fixture_dir, monkeypatch
):
    import api.routes.documents as documents_route
    import services.parser as parser
    from core.database import SessionLocal
    from db.models import DocumentVersion

    # 先阻止后台任务自动执行，观察上传后的初始状态
    monkeypatch.setattr(documents_route, "run_parse_job", lambda version_id: "queued")

    path = fixtures.make_single_column_pdf(fixture_dir / "state-machine.pdf")
    response = upload_pdf(client, workspace_id, "状态机.pdf", path)
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    detail = client.get(f"/api/documents/{version_id}").json()
    assert detail["version"]["parse_status"] == "uploaded"
    assert detail["parse_job"]["status"] == "queued"
    assert detail["parse_job"]["started_at"] is None

    observed = []
    original_extract = parser.extract_document
    original_replace = parser._replace_parsed_content

    def extract_wrapper(path_arg, suffix_arg):
        with SessionLocal() as db:
            observed.append(db.get(DocumentVersion, version_id).parse_status)
        return original_extract(path_arg, suffix_arg)

    def replace_wrapper(db, version, result):
        observed.append(version.parse_status)
        return original_replace(db, version, result)

    monkeypatch.setattr(parser, "extract_document", extract_wrapper)
    monkeypatch.setattr(parser, "_replace_parsed_content", replace_wrapper)

    assert parser.run_parse_job(version_id) == "success"
    assert observed == ["parsing", "indexing"]

    detail = client.get(f"/api/documents/{version_id}").json()
    assert detail["version"]["parse_status"] == "success"
    assert detail["version"]["support_level"] in {"full", "restricted"}
    assert detail["parse_job"]["status"] == "success"
    assert detail["parse_job"]["started_at"]
    assert detail["parse_job"]["finished_at"]
