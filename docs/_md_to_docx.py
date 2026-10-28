"""Minimal Markdown → DOCX converter (stdlib only)."""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

MD = Path(__file__).with_name("智能体基座平台软件需求规格说明书_SRS_V1.2.md")
OUT = Path(__file__).with_name("智能体基座平台软件需求规格说明书_SRS_V1.2.docx")


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def para(text: str, style: str | None = None) -> str:
    t = esc(text)
    if style:
        return (
            f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>'
        )
    return f'<w:p><w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>'


def strip_md(text: str) -> str:
    text = text.replace("**", "")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def build_document_xml(md: str) -> str:
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
        "<w:body>",
    ]
    in_code = False
    for raw in md.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not line.strip():
            parts.append("<w:p/>")
            continue
        text = strip_md(line)
        if in_code:
            parts.append(para(text))
        elif text.startswith("# "):
            parts.append(para(text[2:], "Title"))
        elif text.startswith("## "):
            parts.append(para(text[3:], "Heading1"))
        elif text.startswith("### "):
            parts.append(para(text[4:], "Heading2"))
        elif text.startswith("#### "):
            parts.append(para(text[5:], "Heading3"))
        elif text.startswith("---"):
            continue
        else:
            parts.append(para(text))
    parts.append("<w:sectPr/></w:body></w:document>")
    return "".join(parts)


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal" w:default="1">
    <w:name w:val="Normal"/><w:rPr><w:sz w:val="21"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr>
  </w:style>
</w:styles>
"""


def main() -> None:
    md = MD.read_text(encoding="utf-8")
    document_xml = build_document_xml(md)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
        zf.writestr("word/styles.xml", STYLES)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
