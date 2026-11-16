"""Reject jobs whose title does not match significant search-keyword tokens."""


def significant_keyword_tokens(keyword: str) -> list[str]:
    if keyword.strip() == "*":
        return []
    return [t for part in keyword.lower().split() if len(t := part.strip()) >= 3]


def _token_in_title(token: str, title_lower: str) -> bool:
    if token in title_lower:
        return True
    if len(token) > 3 and token.endswith("s") and token[:-1] in title_lower:
        return True
    return False


def title_matches_keyword(title: str | None, keyword: str) -> bool:
    """All tokens with length >= 3 in keyword must appear in title; '*' passes all."""
    if keyword.strip() == "*":
        return True
    if not title or not title.strip():
        return False
    kw_l = keyword.strip().lower()
    title_lower = title.lower()
    if kw_l in title_lower:
        return True
    tokens = significant_keyword_tokens(keyword)
    if not tokens:
        return True
    return all(_token_in_title(token, title_lower) for token in tokens)