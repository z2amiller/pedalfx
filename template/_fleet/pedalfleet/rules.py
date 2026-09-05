"""Splice the fleet rules block into a project's .kicad_dru without touching local rules."""
import re

BEGIN_RE = re.compile(r"^# --- pedalfx fleet rules v(\d+) begin.*$", re.M)
END_RE = re.compile(r"^# --- pedalfx fleet rules v\d+ end ---[ \t]*$", re.M)
VERSION_RE = re.compile(r"^[ \t]*\(version[ \t]+\d+\)[ \t]*$", re.M)
VERSION_LINE = "(version 1)\n"

CREATED = "created"
INSERTED = "inserted"
REPLACED = "replaced"
UNCHANGED = "unchanged"
MALFORMED = "malformed"


def find_block(text: str):
    """Return (start, end) of the fleet block, None if absent.

    Raises ValueError when only one marker is present or they are out of order.
    The end index includes the newline after the end marker when there is one.
    """
    begin = BEGIN_RE.search(text)
    end = END_RE.search(text)
    if begin is None and end is None:
        return None
    if begin is None or end is None or end.start() < begin.start():
        raise ValueError("fleet rule markers incomplete or out of order")
    stop = end.end()
    if stop < len(text) and text[stop] == "\n":
        stop += 1
    return begin.start(), stop


def block_version(text: str):
    m = BEGIN_RE.search(text)
    return int(m.group(1)) if m else None


def splice(text, block: str):
    """Return (new_text, status). status is one of CREATED/INSERTED/REPLACED/UNCHANGED/MALFORMED.

    MALFORMED returns the input unchanged: the caller must not write it.
    """
    block = block.rstrip("\n") + "\n"
    if text is None or not text.strip():
        return VERSION_LINE + block, CREATED
    versions = list(VERSION_RE.finditer(text))
    if len(versions) != 1:
        return text, MALFORMED
    try:
        span = find_block(text)
    except ValueError:
        return text, MALFORMED
    if span is not None:
        start, stop = span
        if text[start:stop] == block:
            return text, UNCHANGED
        return text[:start] + block + text[stop:], REPLACED
    insert_at = versions[0].end()
    if insert_at < len(text) and text[insert_at] == "\n":
        insert_at += 1
    else:
        block = "\n" + block
    return text[:insert_at] + block + text[insert_at:], INSERTED
