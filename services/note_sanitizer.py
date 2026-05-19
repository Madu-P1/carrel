from __future__ import annotations

import sqlite3

from bs4 import BeautifulSoup, Comment

ALLOWED_NOTE_TAGS = {
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strike",
    "strong",
    "u",
    "ul",
}

DROP_NOTE_TAGS = {
    "applet",
    "audio",
    "canvas",
    "embed",
    "form",
    "iframe",
    "img",
    "input",
    "link",
    "math",
    "meta",
    "object",
    "script",
    "source",
    "style",
    "svg",
    "template",
    "video",
}

RENAMED_NOTE_TAGS = {
    "b": "strong",
    "i": "em",
    "strike": "s",
}


def sanitize_note_html(raw: str | None) -> str:
    """Return the constrained HTML subset Carrel notes are allowed to store."""

    if raw is None or raw == "":
        return "\n"
    if raw == "\n":
        return "\n"

    soup = BeautifulSoup(raw, "html.parser")
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        name = str(tag.name or "").lower()
        if name in DROP_NOTE_TAGS:
            tag.decompose()
            continue
        if name not in ALLOWED_NOTE_TAGS and name not in RENAMED_NOTE_TAGS:
            tag.unwrap()
            continue
        tag.name = RENAMED_NOTE_TAGS.get(name, name)
        tag.attrs = {}

    html = str(soup)
    return "\n" if html.strip() in {"", "<br>", "<br/>"} else html


def sanitize_existing_notes(conn: sqlite3.Connection, *, batch_size: int = 500) -> int:
    """Clean legacy note rows that were persisted before sanitization existed."""

    if not _has_notes_table(conn):
        return 0
    changed_count = 0
    cursor = 0
    while True:
        rows = conn.execute(
            """
            SELECT rowid, id, content
            FROM notes
            WHERE rowid > ?
            ORDER BY rowid ASC
            LIMIT ?
            """,
            (cursor, batch_size),
        ).fetchall()
        if not rows:
            break
        changed: list[tuple[str, str]] = []
        for row in rows:
            cursor = int(row["rowid"])
            clean = sanitize_note_html(row["content"])
            if clean != row["content"]:
                changed.append((clean, row["id"]))
        if changed:
            conn.executemany("UPDATE notes SET content = ? WHERE id = ?", changed)
            changed_count += len(changed)
    if changed_count:
        conn.commit()
    return changed_count


def _has_notes_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'notes'"
    ).fetchone()
    return bool(row)
