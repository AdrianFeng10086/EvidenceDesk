"""TXT 与 Markdown 的段落、字符偏移和状态。"""

from __future__ import annotations

from tests.helpers import upload_bytes, upload_text


def _detail(client, version_id: str) -> dict:
    response = client.get(f"/api/documents/{version_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _content(client, version_id: str) -> dict:
    response = client.get(f"/api/documents/{version_id}/content", params={"page": 1})
    assert response.status_code == 200, response.text
    return response.json()


def test_txt_paragraphs_and_offsets(client, workspace_id):
    content = (
        "第一段：申请人须为副教授。\n"
        "第一段续：并提交研究成果。\n\n"
        "第二段：截止时间为2024年11月15日。\n"
    )
    response = upload_text(client, workspace_id, "制度.txt", content)
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    detail = _detail(client, version_id)
    assert detail["version"]["parse_status"] == "success"
    assert detail["version"]["support_level"] == "full"
    assert detail["version"]["page_count"] == 1

    page = _content(client, version_id)
    assert page["text"] == content
    assert page["spans"]
    for span in page["spans"]:
        assert page["text"][span["char_start"] : span["char_end"]] == span["text"]
        assert span["bboxes"] == []  # 纯文本没有页面坐标

    texts = [span["text"] for span in page["spans"]]
    assert "第一段：申请人须为副教授。\n第一段续：并提交研究成果。" in texts
    assert "第二段：截止时间为2024年11月15日。" in texts


def test_markdown_keeps_headings_lists_and_code_blocks(client, workspace_id):
    content = (
        "# 申报须知\n\n"
        "重点项目申请人须为副教授及以上职称。\n\n"
        "- 提交项目申请书\n"
        "- 提交近三年成果\n\n"
        "```text\n第一行\n\n第二行\n```\n"
    )
    response = upload_text(client, workspace_id, "须知.md", content, media_type="text/markdown")
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    page = _content(client, version_id)
    assert page["text"] == content
    kinds = [span["kind"] for span in page["spans"]]
    assert "heading" in kinds
    assert "list_item" in kinds
    assert "code" in kinds

    code_span = next(span for span in page["spans"] if span["kind"] == "code")
    assert "第一行" in code_span["text"] and "第二行" in code_span["text"]
    assert "\n\n" in code_span["text"], "代码块中的空行不应拆分段落"

    for span in page["spans"]:
        assert page["text"][span["char_start"] : span["char_end"]] == span["text"]


def test_gb18030_text_is_decoded_with_warning(client, workspace_id):
    content = "报销制度：单笔超过5000元需部门负责人审批。\n"
    response = upload_bytes(
        client,
        workspace_id,
        "报销.txt",
        content.encode("gb18030"),
        media_type="text/plain",
    )
    assert response.status_code == 201, response.text
    version_id = response.json()["version"]["id"]

    version = _detail(client, version_id)["version"]
    assert version["parse_status"] == "success"
    assert any(w["code"] == "ENCODING_FALLBACK" for w in version["warnings"])

    page = _content(client, version_id)
    assert "报销制度" in page["text"]
