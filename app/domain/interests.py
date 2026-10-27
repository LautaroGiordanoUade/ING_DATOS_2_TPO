import unicodedata


def normalize_interests(values: list[str]) -> tuple[str, ...]:
    """Canonical profile tags; accents remain significant."""
    result: list[str] = []
    if len(values) > 20:
        raise ValueError("Elegí hasta 20 intereses")
    for value in values:
        normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        if not 1 <= len(normalized) <= 40:
            raise ValueError("Cada interés debe tener entre 1 y 40 caracteres")
        if normalized not in result:
            result.append(normalized)
    return tuple(result)
