from __future__ import annotations

from html import escape
import re


_INLINE_TOKEN = re.compile(
    r"(?P<code>`[^`]+`)|"
    r"(?P<bold>\*\*[^*]+\*\*|__[^_]+__)|"
    r"(?P<italic>\*[^*\n]+\*|_[^_\n]+_)|"
    r"(?P<link>\[[^\]]+\]\([^\)]+\))"
)


def _inline(text: str) -> str:
    """Render the safe inline Markdown subset used by JASPER responses."""
    placeholders: list[str] = []

    def stash(value: str) -> str:
        token = f"\x00{len(placeholders)}\x00"
        placeholders.append(value)
        return token

    text = re.sub(r"\\([\\`*_{}\[\]()#+.!<>|~-])", r"\1", text)
    text = escape(text, quote=False)

    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        if raw.startswith("`"):
            return stash(f'<code>{raw[1:-1]}</code>')
        if raw.startswith("**") or raw.startswith("__"):
            return stash(f"<strong>{raw[2:-2]}</strong>")
        if raw.startswith("["):
            link = re.fullmatch(r"\[([^\]]+)\]\(([^\s\)]+)(?:\s+['\"]([^'\"]*)['\"])?\)", raw)
            if link:
                label, url, title = link.groups()
                safe_url = escape(url, quote=True)
                title_attr = f' title="{escape(title, quote=True)}"' if title else ""
                return stash(f'<a href="{safe_url}"{title_attr}>{label}</a>')
        return stash(f"<em>{raw[1:-1]}</em>")

    text = _INLINE_TOKEN.sub(replace, text)
    for index, value in enumerate(placeholders):
        text = text.replace(f"\x00{index}\x00", value)
    return text


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return len(cells) >= 2 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _table(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2:
        return "".join(f"<p>{_inline(line)}</p>" for line in lines)

    header = rows[0]
    body = rows[2:]
    parts = ['<table><thead><tr>']
    for cell in header:
        parts.append(f"<th>{_inline(cell)}</th>")
    parts.append("</tr></thead>")
    if body:
        parts.append("<tbody>")
        width = len(header)
        for row in body:
            parts.append("<tr>")
            for cell in (row + [""] * width)[:width]:
                parts.append(f"<td>{_inline(cell)}</td>")
            parts.append("</tr>")
        parts.append("</tbody>")
    parts.append("</table>")
    return "".join(parts)


def markdown_to_html(text: str) -> str:
    """Render JASPER Markdown deterministically to Qt-friendly HTML.

    This intentionally supports the response subset JASPER needs instead of
    relying on Qt's Markdown parser, whose table handling is inconsistent.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            content = "<br>".join(_inline(line) for line in paragraph)
            out.append(f"<p>{content}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_paragraph()
            fence = stripped[:3]
            language = stripped[3:].strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            lang_attr = f' data-language="{escape(language, quote=True)}"' if language else ""
            out.append(f"<pre><code{lang_attr}>{escape(chr(10).join(code_lines))}</code></pre>")
            continue

        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*$", stripped)
        if heading:
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            out.append(f"<h{level}>{_inline(heading.group(1))}</h{level}>")
            index += 1
            continue

        if re.fullmatch(r"[-*_](?:\s*[-*_]){2,}", stripped):
            flush_paragraph()
            out.append("<hr>")
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            out.append(f"<blockquote>{'<br>'.join(_inline(line) for line in quote_lines)}</blockquote>")
            continue

        if "|" in stripped and index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            flush_paragraph()
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            out.append(_table(table_lines))
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            ordered_list = ordered is not None
            tag = "ol" if ordered_list else "ul"
            items: list[str] = []
            pattern = r"^\s*\d+[.)]\s+(.+)$" if ordered_list else r"^\s*[-*+]\s+(.+)$"
            while index < len(lines):
                match = re.match(pattern, lines[index])
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    return "".join(out)
