import unicodedata


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().lower()
