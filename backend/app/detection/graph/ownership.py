from collections import defaultdict


def ownership_groups(owners: dict[str, str | None], min_providers: int = 2) -> list[dict]:
    """Providers that share a recorded owner. Used as context on a case: common ownership makes a
    referral loop easier to explain innocently and also easier to coordinate."""
    groups: dict[str, list[str]] = defaultdict(list)
    for provider_id, owner in owners.items():
        if owner:
            groups[owner].append(provider_id)
    return [{"owner_id": owner, "providers": sorted(ids)} for owner, ids in groups.items() if len(ids) >= min_providers]


def common_owner(owners: dict[str, str | None], providers: list[str]) -> str | None:
    found = {owners.get(p) for p in providers}
    return found.pop() if len(found) == 1 and None not in found else None
