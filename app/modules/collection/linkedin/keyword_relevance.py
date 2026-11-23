"""Reject jobs whose title does not match significant search-keyword tokens."""

# Deterministic equivalences (engineer ↔ developer, etc.) — tested in unit tests.
_ROLE_EQUIVALENCE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"engineer", "developer", "dev"}),
    frozenset({"frontend", "front-end"}),
    frozenset({"backend", "back-end"}),
    frozenset({"fullstack", "full-stack"}),
    frozenset({"nodejs", "node.js"}),
    frozenset({"ui/ux", "ui", "ux"}),
)


def significant_keyword_tokens(keyword: str) -> list[str]:
    if keyword.strip() == "*":
        return []
    return [t for part in keyword.lower().split() if len(t := part.strip()) >= 3]


def _equivalence_variants(token: str) -> set[str]:
    token_l = token.lower()
    variants = {token_l}
    if len(token_l) > 3 and token_l.endswith("s"):
        variants.add(token_l[:-1])
    for group in _ROLE_EQUIVALENCE_GROUPS:
        if token_l in group:
            variants |= group
    return variants


def _token_in_title(token: str, title_lower: str) -> bool:
    for variant in _equivalence_variants(token):
        if variant in title_lower:
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
    # Compound roles: allow engineer/developer swap when keyword includes those tokens.
    role_swap = {"engineer", "developer", "dev"}
    if any(t in role_swap for t in tokens):
        alt_phrases = []
        if "engineer" in tokens:
            alt_phrases.append(kw_l.replace("engineer", "developer"))
        if "developer" in tokens or "dev" in tokens:
            alt_phrases.append(kw_l.replace("developer", "engineer").replace(" dev ", " engineer "))
        for phrase in alt_phrases:
            if phrase and phrase in title_lower:
                return True
    return all(_token_in_title(token, title_lower) for token in tokens)