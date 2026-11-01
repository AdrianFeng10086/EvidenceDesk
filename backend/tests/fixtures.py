"""测试用文档生成器。

优先使用中文字体；如果运行环境没有 CJK 字体则退回英文内容，
保证测试在任何机器上都能验证解析逻辑（不验证具体字形）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

CJK_FONT_PATH = next(
    (
        path
        for path in (
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        )
        if os.path.exists(path)
    ),
    None,
)
FONT_NAME = "Helvetica"
USE_CJK = CJK_FONT_PATH is not None

if USE_CJK:
    try:
        pdfmetrics.registerFont(TTFont("EvidenceCJK", CJK_FONT_PATH))
        FONT_NAME = "EvidenceCJK"
    except Exception:  # noqa: BLE001 — .ttc 子字体差异时退回英文
        USE_CJK = False
        FONT_NAME = "Helvetica"


def _t(zh: str, en: str) -> str:
    return zh if USE_CJK else en


def localized(zh: str, en: str) -> str:
    return _t(zh, en)


def make_text_pdf(path: Path, lines: Iterable[str], font_size: int = 11) -> Path:
    c = _canvas(path)
    c.setFont(FONT_NAME, font_size)
    for index, line in enumerate(lines):
        c.drawString(72, 760 - index * 22, line)
    c.save()
    return path


HEADING = _t("科研项目申报指南", "Research Project Application Guide")
BODY_1 = _t(
    "重点项目申请人须为副教授及以上职称，并提交近三年研究成果。",
    "Key project applicants must be associate professors or above and submit research outputs from the last three years.",
)
BODY_2 = _t(
    "申报截止时间为2024年11月15日，逾期不予受理。",
    "The application deadline is November 15, 2024. Late submissions will not be accepted.",
)
HEADING_2 = _t("第二章 申报材料", "Chapter 2: Application Materials")
LIST_ITEM = _t("1. 项目申请书（一式三份）。", "1. Project application form (three copies).")
PAGE_2_HEADING = _t("第三章 评审流程", "Chapter 3: Review Process")
PAGE_2_BODY = _t(
    "评审分为形式审查与专家评审两个阶段。",
    "The review has two stages: formal review and expert review.",
)

LEFT_LINES = [
    _t("左栏第一行：项目申报条件。", "Left column line one: eligibility."),
    _t("左栏第二行：申请人资格要求。", "Left column line two: applicant qualifications."),
    _t("左栏第三行：材料提交方式。", "Left column line three: submission."),
    _t("左栏第四行：截止时间说明。", "Left column line four: deadline."),
]
RIGHT_LINES = [
    _t("右栏第一行：评审标准说明。", "Right column line one: review criteria."),
    _t("右栏第二行：专家评审流程。", "Right column line two: expert review."),
    _t("右栏第三行：结果公示安排。", "Right column line three: result publication."),
    _t("右栏第四行：异议处理方式。", "Right column line four: objections."),
]

TABLE_TEXT = _t("申报截止时间", "Application deadline")
TABLE_VALUE = _t("2024年11月15日", "November 15, 2024")


def _canvas(path: Path) -> canvas.Canvas:
    return canvas.Canvas(str(path), pagesize=A4)


def make_single_column_pdf(path: Path) -> Path:
    c = _canvas(path)
    c.setFont(FONT_NAME, 16)
    c.drawString(72, 760, HEADING)
    c.setFont(FONT_NAME, 11)
    c.drawString(72, 730, BODY_1)
    c.drawString(72, 712, BODY_2)
    c.setFont(FONT_NAME, 13)
    c.drawString(72, 670, HEADING_2)
    c.setFont(FONT_NAME, 11)
    c.drawString(72, 650, LIST_ITEM)
    c.showPage()

    c.setFont(FONT_NAME, 14)
    c.drawString(72, 760, PAGE_2_HEADING)
    c.setFont(FONT_NAME, 11)
    c.drawString(72, 730, PAGE_2_BODY)
    c.save()
    return path


def make_two_column_pdf(path: Path) -> Path:
    c = _canvas(path)
    c.setFont(FONT_NAME, 11)
    for index, text in enumerate(LEFT_LINES):
        c.drawString(72, 760 - index * 20, text)
    for index, text in enumerate(RIGHT_LINES):
        c.drawString(330, 760 - index * 20, text)
    c.save()
    return path


def make_table_pdf(path: Path) -> Path:
    c = _canvas(path)
    c.setFont(FONT_NAME, 13)
    c.drawString(72, 780, _t("申报信息表", "Application Information"))
    data = [
        [_t("事项", "Item"), _t("内容", "Value")],
        [TABLE_TEXT, TABLE_VALUE],
        [_t("受理单位", "Office"), _t("科研管理处", "Research Office")],
    ]
    table = Table(data, colWidths=[140, 220])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    table.wrapOn(c, 400, 200)
    table.drawOn(c, 72, 620)
    c.save()
    return path


def make_scanned_pdf(path: Path, work_dir: Path) -> Path:
    from PIL import Image, ImageDraw

    image_path = work_dir / "scan.png"
    image = Image.new("RGB", (800, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 760, 460], outline="black", width=3)
    draw.text((80, 120), "SCANNED PAGE - NO TEXT LAYER", fill="black")
    image.save(image_path)

    c = _canvas(path)
    c.drawImage(str(image_path), 72, 420, width=450, height=280)
    c.save()
    return path


def make_blank_pdf(path: Path) -> Path:
    c = _canvas(path)
    c.showPage()
    c.save()
    return path


def make_encrypted_pdf(path: Path, work_dir: Path) -> Path:
    from pypdf import PdfReader, PdfWriter

    plain = make_single_column_pdf(work_dir / "plain-for-encrypt.pdf")
    reader = PdfReader(str(plain))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("secret-password")
    with path.open("wb") as target:
        writer.write(target)
    return path


def make_corrupt_pdf(path: Path) -> Path:
    path.write_bytes(b"This is not a PDF file at all.\n" * 10)
    return path


def make_txt(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def make_markdown(path: Path) -> Path:
    path.write_text(
        "# 申报须知\n\n"
        "重点项目申请人须为副教授及以上职称。\n\n"
        "- 提交项目申请书\n"
        "- 提交近三年成果\n\n"
        "```text\n保留代码块中的空行\n\n不会被拆成两个段落\n```\n",
        encoding="utf-8",
    )
    return path
