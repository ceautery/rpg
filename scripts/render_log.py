#!/usr/bin/env python3
"""
Converts log/session.md to log/session.html — a self-contained, auto-refreshing watch view.
Run any time during or after a session:
  python scripts/render_log.py

The HTML file refreshes every 5 seconds, so an open browser tab stays live.
No external dependencies — pure stdlib string templating.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

INPUT = Path(__file__).parent.parent / "log" / "session.md"
OUTPUT = Path(__file__).parent.parent / "log" / "session.html"
REFRESH_SECONDS = 5

CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #13100c;
    color: #cfc4a0;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 16px;
    line-height: 1.75;
    max-width: 820px;
    margin: 0 auto;
    padding: 48px 28px 100px;
  }
  h1 {
    color: #d4a843;
    font-size: 1.55em;
    letter-spacing: 0.03em;
    border-bottom: 1px solid #3a3020;
    padding-bottom: 10px;
    margin-bottom: 20px;
  }
  h2 {
    color: #c89c3a;
    font-size: 1.1em;
    font-variant: small-caps;
    letter-spacing: 0.06em;
    margin: 2.2em 0 0.6em;
    padding-left: 12px;
    border-left: 3px solid #6b4f10;
  }
  hr {
    border: none;
    border-top: 1px solid #2c2418;
    margin: 1.8em 0;
  }
  p {
    margin: 0.6em 0;
  }
  em { color: #a89870; font-style: italic; }
  strong { color: #e0d4a8; font-weight: bold; }
  ul { padding-left: 1.6em; margin: 0.4em 0; }
  li { margin: 3px 0; }
  .meta {
    color: #6e6048;
    font-style: italic;
    font-size: 0.88em;
    margin: 2px 0;
  }
  .roll-block {
    background: #0c0a07;
    border: 1px solid #2c2418;
    border-left: 3px solid #4a3a18;
    border-radius: 3px;
    padding: 9px 14px;
    margin: 10px 0;
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.85em;
    line-height: 1.6;
  }
  .roll-line { color: #9a8c68; margin: 2px 0; }
  .hit  { color: #6ab86a; font-weight: bold; }
  .miss { color: #b86a6a; font-weight: bold; }
  .auto { color: #6a9ab8; font-weight: bold; }
  .scene-note {
    color: #6e6048;
    font-style: italic;
    font-size: 0.9em;
    margin: 0.8em 0;
  }
  .refresh-badge {
    position: fixed;
    bottom: 16px;
    right: 20px;
    background: #1e1810;
    border: 1px solid #3a3020;
    color: #5a5038;
    font-family: monospace;
    font-size: 0.75em;
    padding: 4px 10px;
    border-radius: 3px;
  }
"""

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{refresh}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
{css}
  </style>
</head>
<body>
{body}
<div class="refresh-badge">auto-refresh {refresh}s</div>
</body>
</html>
"""


# ── Inline formatting ────────────────────────────────────────────────────────

def apply_inline(text: str) -> str:
    """Convert **bold**, *italic*, and escape HTML special chars."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold before italic so **x** doesn't get mangled by *x* pass
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", text)
    return text


def apply_roll_highlighting(html: str) -> str:
    """Add colour spans to → HIT, → MISS, and auto-hit markers."""
    html = re.sub(r"→\s*(HIT)", r'→ <span class="hit">\1</span>', html)
    html = re.sub(r"→\s*(MISS)", r'→ <span class="miss">\1</span>', html)
    html = re.sub(r"\b(auto-hit|auto-miss)\b", r'<span class="auto">\1</span>', html, flags=re.I)
    return html


# ── Block classification ─────────────────────────────────────────────────────

def is_roll_line(line: str) -> bool:
    """True for lines that belong inside a roll-block."""
    s = line.lstrip()
    # "- r1 ·", "- **Total", "- **Sum", "- **Magic"
    return bool(re.match(r"^-\s+(r\d|r[a-z]|\*\*(Total|Sum|Magic|Net|Damage|Result))", s))


def is_list_line(line: str) -> bool:
    return line.startswith("- ") and not is_roll_line(line)


def is_meta_line(line: str) -> bool:
    """Italicised single-line annotations like *Scene cleared.* or *Round 2...*"""
    s = line.strip()
    return s.startswith("*") and s.endswith("*") and not s.startswith("**")


# ── Converter ────────────────────────────────────────────────────────────────

def convert(md: str) -> tuple[str, str]:
    """Return (title, html_body)."""
    lines = md.splitlines()
    out: list[str] = []
    title = "Session Log"

    in_roll_block = False
    in_list = False
    i = 0

    def close_roll():
        nonlocal in_roll_block
        if in_roll_block:
            out.append("</div>")
            in_roll_block = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # H1
        if stripped.startswith("# ") and not stripped.startswith("## "):
            close_roll(); close_list()
            text = apply_inline(stripped[2:])
            title = stripped[2:]
            out.append(f"<h1>{text}</h1>")

        # H2
        elif stripped.startswith("## "):
            close_roll(); close_list()
            out.append(f'<h2>{apply_inline(stripped[3:])}</h2>')

        # HR
        elif stripped == "---":
            close_roll(); close_list()
            out.append("<hr>")

        # Blank line
        elif stripped == "":
            close_roll(); close_list()
            out.append("")

        # Roll line → open/extend roll block
        elif is_roll_line(stripped):
            close_list()
            if not in_roll_block:
                out.append('<div class="roll-block">')
                in_roll_block = True
            rendered = apply_roll_highlighting(apply_inline(stripped[2:]))
            out.append(f'  <div class="roll-line">· {rendered}</div>')

        # List item
        elif is_list_line(stripped):
            close_roll()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"  <li>{apply_inline(stripped[2:])}</li>")

        # Meta / scene-note line
        elif is_meta_line(stripped):
            close_roll(); close_list()
            inner = apply_inline(stripped[1:-1])
            out.append(f'<p class="scene-note"><em>{inner}</em></p>')

        # Regular paragraph
        else:
            close_roll(); close_list()
            if stripped:
                out.append(f"<p>{apply_inline(stripped)}</p>")

        i += 1

    close_roll()
    close_list()

    return title, "\n".join(out)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if not INPUT.exists():
        print(f"Error: {INPUT} not found", file=sys.stderr)
        sys.exit(1)

    md = INPUT.read_text(encoding="utf-8")
    title, body = convert(md)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body += f'\n<p class="meta" style="margin-top:3em">Rendered {ts} from session.md</p>'

    html = HTML_TEMPLATE.format(
        refresh=REFRESH_SECONDS,
        title=title,
        css=CSS,
        body=body,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written → {OUTPUT}  ({len(html):,} bytes, refreshes every {REFRESH_SECONDS}s)")


if __name__ == "__main__":
    main()
