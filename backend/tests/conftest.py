"""测试环境：每次运行使用独立的临时数据库与上传目录。"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_ROOT = Path(tempfile.mkdtemp(prefix="evidence-desk-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["DEMO_MODE"] = "true"
os.environ["DEMO_WORKSPACE_ID"] = "demo_workspace"
os.environ["DEMO_USER_ID"] = "demo_user"
os.environ["MAX_TEXT_SIZE_MB"] = "1"
os.environ["MAX_PDF_SIZE_MB"] = "10"
os.environ["MAX_PDF_PAGES"] = "30"
os.environ["MAX_DOCUMENTS_PER_WORKSPACE"] = "10"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    path = TEST_ROOT / "fixtures"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def workspace_id(client) -> str:
    response = client.post(
        "/api/workspaces",
        json={"name": f"测试资料空间-{uuid.uuid4().hex[:8]}", "description": "pytest"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


DEMO_WORKSPACE_ID = os.environ["DEMO_WORKSPACE_ID"]


@pytest.fixture()
def intruder_headers() -> dict:
    return {"X-Demo-User": "intruder"}
