"""
Utilities for string normalization used across the project.
"""

import unicodedata


def normalize(s: str | None) -> str:
    """Normalize text for matching and column detection.

    - Converts to str
    - Strips leading/trailing whitespace
    - Lowercases
    - Removes diacritics
    - Collapses multiple spaces
    """
    if s is None:
        return ""
    s = str(s)
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    # remove combining characters (accents)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # collapse whitespace
    s = " ".join(s.split())
    return s
