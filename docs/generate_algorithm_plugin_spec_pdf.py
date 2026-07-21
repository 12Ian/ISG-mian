"""从 ALGORITHM_PLUGIN_SPEC.md 生成软件内置的插件规范 PDF。"""
from __future__ import annotations

import re
import shutil
import textwrap
from datetime import date
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "ALGORITHM_PLUGIN_SPEC.md"
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT_PDF = OUTPUT_DIR / "ISG算法插件开发规范_专业版.pdf"
APP_PDF = ROOT / "docs" / "ISG算法插件开发规范_专业版.pdf"
VERSIONED_PDF = ROOT / "docs" / "ISG 算法插件开发规范 v2.0.pdf"
COMMON_TEMPLATE = ROOT / "plugins" / "user" / "_TEMPLATE.py"
TRAINING_TEMPLATE = ROOT / "plugins" / "user" / "_TRAINING_TEMPLATE.py"


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("ISG-CN", r"C:\Windows\Fonts\simhei.ttf"))
    pdfmetrics.registerFont(TTFont("ISG-Code", r"C:\Windows\Fonts\consola.ttf"))


def inline_markup(text: str) -> str:
    escaped = escape(text.strip())
    escaped = re.sub(
        r"`([^`]+)`",
        r'<font name="ISG-CN" color="#0F5C78">\1</font>',
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCN",
            parent=base["Title"],
            fontName="ISG-CN",
            fontSize=25,
            leading=34,
            textColor=colors.HexColor("#123B52"),
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCN",
            parent=base["Normal"],
            fontName="ISG-CN",
            fontSize=11,
            leading=18,
            textColor=colors.HexColor("#5E7480"),
            alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "H1CN",
            parent=base["Heading1"],
            fontName="ISG-CN",
            fontSize=20,
            leading=27,
            textColor=colors.HexColor("#123B52"),
            spaceBefore=5,
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "H2CN",
            parent=base["Heading2"],
            fontName="ISG-CN",
            fontSize=14,
            leading=20,
            textColor=colors.HexColor("#007C91"),
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3CN",
            parent=base["Heading3"],
            fontName="ISG-CN",
            fontSize=12,
            leading=18,
            textColor=colors.HexColor("#2B5B6D"),
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "BodyCN",
            parent=base["BodyText"],
            fontName="ISG-CN",
            fontSize=9.2,
            leading=15.5,
            textColor=colors.HexColor("#26373F"),
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "BulletCN",
            parent=base["BodyText"],
            fontName="ISG-CN",
            fontSize=9.1,
            leading=15,
            leftIndent=14,
            firstLineIndent=-8,
            textColor=colors.HexColor("#26373F"),
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "CodeCN",
            parent=base["Code"],
            fontName="ISG-CN",
            fontSize=7.4,
            leading=10.5,
            leftIndent=7,
            rightIndent=7,
            borderColor=colors.HexColor("#C7D5DB"),
            borderWidth=0.5,
            borderPadding=7,
            backColor=colors.HexColor("#F3F7F8"),
            textColor=colors.HexColor("#18343F"),
            spaceBefore=4,
            spaceAfter=8,
        ),
        "toc": ParagraphStyle(
            "TocCN",
            parent=base["BodyText"],
            fontName="ISG-CN",
            fontSize=10,
            leading=17,
            leftIndent=12,
            textColor=colors.HexColor("#274D5D"),
        ),
        "table": ParagraphStyle(
            "TableCN",
            parent=base["BodyText"],
            fontName="ISG-CN",
            fontSize=7.6,
            leading=11,
            textColor=colors.HexColor("#26373F"),
        ),
    }


def parse_table(lines: list[str], styles: dict[str, ParagraphStyle]) -> Table:
    rows = []
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if index == 1 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append([Paragraph(inline_markup(cell), styles["table"]) for cell in cells])

    column_count = max(len(row) for row in rows)
    available = A4[0] - 38 * mm
    if column_count == 2:
        widths = [available * 0.28, available * 0.72]
    elif column_count == 3:
        widths = [available * 0.2, available * 0.25, available * 0.55]
    elif column_count == 4:
        widths = [available * 0.17, available * 0.16, available * 0.12, available * 0.55]
    else:
        widths = [available / column_count] * column_count

    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCECEF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#123B52")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C9CF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFB")]),
    ]))
    return table


def wrap_code_text(code: str, width: int = 92) -> str:
    wrapped = []
    for code_line in code.expandtabs(4).splitlines():
        indent = len(code_line) - len(code_line.lstrip(" "))
        parts = textwrap.wrap(
            code_line,
            width=width,
            subsequent_indent=" " * min(indent + 4, 24),
            replace_whitespace=False,
            drop_whitespace=False,
        )
        wrapped.extend(parts or [""])
    return "\n".join(wrapped)


def markdown_story(markdown: str, styles: dict[str, ParagraphStyle]) -> list:
    lines = markdown.splitlines()
    story = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code = False
    index = 0

    def flush_paragraph() -> None:
        if paragraph_lines:
            story.append(Paragraph(inline_markup(" ".join(paragraph_lines)), styles["body"]))
            paragraph_lines.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            if in_code:
                story.append(XPreformatted(wrap_code_text("\n".join(code_lines)), styles["code"]))
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line.expandtabs(4))
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped == "<!-- PAGEBREAK -->":
            flush_paragraph()
            story.append(PageBreak())
            index += 1
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
            flush_paragraph()
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            story.append(parse_table(table_lines, styles))
            story.append(Spacer(1, 7))
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(stripped[2:]), styles["h1"]))
        elif stripped.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(stripped[3:]), styles["h2"]))
        elif stripped.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(stripped[4:]), styles["h3"]))
        elif re.match(r"^[-*] \[[ xX]\] ", stripped):
            flush_paragraph()
            checked = stripped[3].lower() == "x"
            text = stripped[6:]
            story.append(Paragraph(("[完成] " if checked else "[ ] ") + inline_markup(text), styles["bullet"]))
        elif re.match(r"^[-*] ", stripped):
            flush_paragraph()
            story.append(Paragraph("- " + inline_markup(stripped[2:]), styles["bullet"]))
        elif re.match(r"^\d+\. ", stripped):
            flush_paragraph()
            number, text = stripped.split(". ", 1)
            story.append(Paragraph(number + ". " + inline_markup(text), styles["bullet"]))
        else:
            paragraph_lines.append(stripped)
        index += 1

    flush_paragraph()
    return story


def draw_page(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#B9CDD4"))
    canvas.setLineWidth(0.4)
    canvas.line(19 * mm, height - 14 * mm, width - 19 * mm, height - 14 * mm)
    canvas.setFont("ISG-CN", 7.5)
    canvas.setFillColor(colors.HexColor("#657B84"))
    canvas.drawString(19 * mm, height - 10.5 * mm, "ISG 算法插件开发规范 v2.0")
    canvas.drawRightString(width - 19 * mm, 10 * mm, f"第 {document.page} 页")
    canvas.restoreState()


def build_pdf() -> None:
    register_fonts()
    styles = build_styles()
    markdown = SOURCE.read_text(encoding="utf-8")
    section_titles = [
        line[3:].strip()
        for line in markdown.splitlines()
        if line.startswith("## ")
    ]
    section_titles.extend(["附录 A：普通插件模板完整源码", "附录 B：训练插件模板完整源码"])

    story = [
        Spacer(1, 48 * mm),
        Paragraph("ISG 算法插件开发规范", styles["title"]),
        Paragraph("Version 2.0", styles["subtitle"]),
        Spacer(1, 8 * mm),
        Paragraph(
            "覆盖普通插件、训练插件、数据集兼容性、模型权重、离线日志、标签转换、取消处理和 checkpoint 输出。",
            styles["subtitle"],
        ),
        Spacer(1, 55 * mm),
        Paragraph(f"生成日期：{date.today().isoformat()}", styles["subtitle"]),
        PageBreak(),
        Paragraph("目录", styles["h1"]),
    ]
    story.extend(Paragraph(title, styles["toc"]) for title in section_titles)
    story.append(PageBreak())
    story.extend(markdown_story(markdown, styles))
    story.extend([
        PageBreak(),
        Paragraph("附录 A：普通插件模板完整源码", styles["h1"]),
        Paragraph("文件：plugins/user/_TEMPLATE.py", styles["body"]),
        XPreformatted(
            wrap_code_text(COMMON_TEMPLATE.read_text(encoding="utf-8")),
            styles["code"],
        ),
        PageBreak(),
        Paragraph("附录 B：训练插件模板完整源码", styles["h1"]),
        Paragraph("文件：plugins/user/_TRAINING_TEMPLATE.py", styles["body"]),
        XPreformatted(
            wrap_code_text(TRAINING_TEMPLATE.read_text(encoding="utf-8")),
            styles["code"],
        ),
    ])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        rightMargin=19 * mm,
        leftMargin=19 * mm,
        topMargin=20 * mm,
        bottomMargin=17 * mm,
        title="ISG 算法插件开发规范 v2.0",
        author="ISG",
        subject="ISG Python 算法插件接口和训练插件规范",
    )
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    shutil.copy2(OUTPUT_PDF, APP_PDF)
    shutil.copy2(OUTPUT_PDF, VERSIONED_PDF)


if __name__ == "__main__":
    build_pdf()
    print(OUTPUT_PDF)
