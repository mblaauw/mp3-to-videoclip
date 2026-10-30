"""Find a person's words in their own text, forgiving only how a model retypes them.

Line breaks and curly quotes change when text passes through a model, so a match
allows for those and nothing else. Callers keep the slice of the original text,
never the model's copy.
"""

from __future__ import annotations

import re

_SWAPS = {
    "'": "['‘’]",
    "‘": "['‘’]",
    "’": "['‘’]",
    '"': '["“”]',
    "“": '["“”]',
    "”": '["“”]',
    "-": "[-–—]",
    "–": "[-–—]",
    "—": "[-–—]",
}


def pattern(fragment: str) -> re.Pattern[str]:
    words = (
        "".join(_SWAPS.get(char, re.escape(char)) for char in word) for word in fragment.split()
    )
    return re.compile(r"\s+".join(words))


def words(text: str) -> list[str]:
    return text.split()
