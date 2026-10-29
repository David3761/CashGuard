"""Language detection (A11): S0 stub of `detect_language`.

A11 replaces the body (diacritics + RO/EN stopwords; short or ambiguous text keeps the current
language). The stub always keeps the current language, so bomboe's `/chat` (B9) can call it now.
"""

from app.domain.enums import Language


def detect_language(text: str, current: Language) -> Language:
    """Stub of A11: keeps `current`."""
    return current
