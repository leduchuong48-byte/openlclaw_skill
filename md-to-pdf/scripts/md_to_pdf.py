#!/usr/bin/env python3
"""
Markdown -> printable PDF converter with solid table rendering.

Pipeline:
1) Markdown to HTML (python-markdown)
2) HTML/CSS to PDF (WeasyPrint)

If dependencies are missing, the script bootstraps pip and installs them.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import re
import subprocess
import sys
from pathlib import Path


def _ensure_python_deps() -> None:
    required = {
        "markdown": "markdown>=3.6,<4",
        "weasyprint": "weasyprint>=66,<67",
    }

    missing = [spec for module, spec in required.items() if importlib.util.find_spec(module) is None]
    if not missing:
        return

    try:
        import pip  # noqa: F401
    except Exception:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])

    cmd = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
    subprocess.check_call(cmd)


_ensure_python_deps()

import markdown  # type: ignore  # noqa: E402
from weasyprint import HTML  # type: ignore  # noqa: E402


PRINT_CSS = """
@page {
  size: A4;
  margin: 16mm 14mm 18mm 14mm;

  @bottom-right {
    content: "第 " counter(page) " / " counter(pages) " 页";
    font-size: 9pt;
    color: #666;
  }
}

html, body {
  margin: 0;
  padding: 0;
}

body {
  font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 11pt;
  line-height: 1.65;
  color: #202124;
}

.article {
  width: 100%;
}

h1, h2, h3, h4, h5, h6 {
  font-family: "Noto Serif CJK SC", "Songti SC", serif;
  color: #111;
  margin: 1.2em 0 0.55em;
  line-height: 1.35;
  page-break-after: avoid;
}

h1 {
  font-size: 22pt;
  border-bottom: 2px solid #e8eaed;
  padding-bottom: 0.2em;
}

h2 { font-size: 17pt; }
h3 { font-size: 14pt; }

p {
  margin: 0.58em 0;
  widows: 2;
  orphans: 2;
}

ul, ol {
  margin: 0.45em 0 0.7em 1.2em;
  padding: 0;
}

li {
  margin: 0.25em 0;
}

blockquote {
  margin: 0.9em 0;
  padding: 0.2em 0.9em;
  border-left: 3px solid #d0d7de;
  color: #57606a;
  background: #f8f9fa;
}

code {
  font-family: "JetBrains Mono", "Fira Code", "SFMono-Regular", Consolas, monospace;
  font-size: 9.2pt;
  background: #f5f7fb;
  border: 1px solid #e6e9ef;
  border-radius: 3px;
  padding: 0.08em 0.35em;
}

pre {
  margin: 0.9em 0;
  background: #f7f9fc;
  border: 1px solid #e6e9ef;
  border-radius: 6px;
  padding: 0.7em 0.85em;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-word;
  page-break-inside: avoid;
}

pre code {
  border: 0;
  background: transparent;
  padding: 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.95em 0 1.1em;
  table-layout: fixed;
  page-break-inside: auto;
}

thead {
  display: table-header-group;
}

tfoot {
  display: table-footer-group;
}

tr {
  page-break-inside: avoid;
  page-break-after: auto;
}

th, td {
  border: 1px solid #c7cdd6;
  padding: 7px 8px;
  vertical-align: top;
  word-break: break-word;
  overflow-wrap: anywhere;
  text-align: left;
}

th {
  background: #eef2f7;
  color: #111;
  font-weight: 700;
}

tbody tr:nth-child(even) td {
  background: #fafbfc;
}

a {
  color: #0b57d0;
  text-decoration: none;
}

hr {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 1.1em 0;
}
""".strip()


def _derive_title(markdown_text: str, fallback: str) -> str:
    for line in markdown_text.splitlines():
        m = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return fallback


def _preprocess_markdown(markdown_text: str) -> str:
    text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    # Task list fallback (without extra extension)
    text = re.sub(r"^\s*[-*+]\s+\[\s\]\s+", "- ☐ ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+\[[xX]\]\s+", "- ☑ ", text, flags=re.MULTILINE)
    return text


def _markdown_to_html(markdown_text: str, title: str) -> str:
    body_html = markdown.markdown(
        markdown_text,
        extensions=[
            "extra",         # includes tables, fenced_code, sane lists, etc.
            "sane_lists",
            "nl2br",
        ],
        output_format="html5",
    )

    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>{safe_title}</title>
  <style>{PRINT_CSS}</style>
</head>
<body>
  <article class=\"article\">{body_html}</article>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Markdown text to printable PDF.")
    parser.add_argument("--input-file", required=True, help="Input markdown file path")
    parser.add_argument("--output-file", required=True, help="Output PDF file path")
    parser.add_argument("--title", default="", help="Optional document title")
    args = parser.parse_args()

    input_path = Path(args.input_file).expanduser().resolve()
    output_path = Path(args.output_file).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    markdown_text = input_path.read_text(encoding="utf-8")
    markdown_text = _preprocess_markdown(markdown_text)
    title = args.title.strip() or _derive_title(markdown_text, fallback=input_path.stem)

    html_doc = _markdown_to_html(markdown_text, title=title)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_doc, base_url=str(input_path.parent)).write_pdf(str(output_path))

    print(f"PDF generated: {output_path}")
    print("engine=weasyprint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
