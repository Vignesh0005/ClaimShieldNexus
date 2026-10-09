import re
from difflib import SequenceMatcher


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_key(a), normalize_key(b)).ratio()


def normalize_address(address: str | None) -> str:
    if not address:
        return ""
    text = address.lower()
    for long, short in (("street", "st"), ("avenue", "ave"), ("suite", "ste"), ("road", "rd"), ("boulevard", "blvd"), ("floor", "fl")):
        text = re.sub(rf"\b{long}\b", short, text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()
