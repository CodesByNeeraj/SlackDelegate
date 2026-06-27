from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.6


def _score(raw: str, candidate: str) -> float:
    raw_l = raw.lower().strip()
    cand_l = candidate.lower().strip()
    if not cand_l:
        return 0.0
    # Word-level: any exact word overlap handles "Julio" matching "Julio Martinez"
    if set(raw_l.split()) & set(cand_l.split()):
        return 0.9
    return SequenceMatcher(None, raw_l, cand_l).ratio()


def match_name_to_slack_user(raw_name: str, slack_users: list[dict]) -> str | None:
    """Returns the Slack user_id of the best match, or None if nothing clears the threshold."""
    best_score = 0.0
    best_id = None

    for user in slack_users:
        if user.get("deleted") or user.get("is_bot") or user.get("id") == "USLACKBOT":
            continue
        profile = user.get("profile", {})
        for candidate in (profile.get("real_name", ""), profile.get("display_name", "")):
            s = _score(raw_name, candidate)
            if s > best_score:
                best_score = s
                best_id = user["id"]

    return best_id if best_score >= MATCH_THRESHOLD else None
