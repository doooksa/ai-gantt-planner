"""Deterministic slug generation for task ids (id = slug or uuid per spec).

Handles Cyrillic by transliteration so ids stay URL/JSON friendly. Falls back
to a positional id when a name has no usable characters.
"""

from __future__ import annotations

import re

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _transliterate(text: str) -> str:
    return "".join(_CYR.get(ch, _CYR.get(ch.lower(), ch)) if ch.lower() in _CYR else ch
                   for ch in text)


def slugify(name: str) -> str:
    base = _transliterate(name).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base


def unique_slug(name: str, existing: set[str], *, index: int = 0) -> str:
    """A slug for `name` guaranteed not to collide with `existing`."""
    base = slugify(name) or f"task-{index + 1}"
    candidate = base
    n = 2
    while candidate in existing:
        candidate = f"{base}-{n}"
        n += 1
    return candidate
