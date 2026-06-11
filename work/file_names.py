from __future__ import annotations

import hashlib
import re


SHEET_SLUGS = {
    "시·도지사": "governor",
    "구·시·군의장": "mayor",
    "시·도의회의원": "sido_council",
    "구·시·군의회의원": "sigungu_council",
    "광역의원비례대표": "sido_pr",
    "기초의원비례대표": "sigungu_pr",
    "교육감": "education_superintendent",
    "교육의원": "education_council",
}


def safe_component(value: object, *, default: str = "value", max_length: int = 48) -> str:
    text = "" if value is None else str(value)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    if not slug:
        slug = default
    if len(slug) > max_length:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        slug = f"{slug[: max_length - 9].rstrip('-._')}-{digest}"
    return slug


def sheet_slug(sheet: object) -> str:
    text = "" if sheet is None else str(sheet)
    return safe_component(SHEET_SLUGS.get(text, text), default="sheet", max_length=40)
