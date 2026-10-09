from collections import defaultdict

from app.utils.fuzzy import normalize_address


def shared_address_groups(addresses: dict[str, str | None], min_providers: int = 3) -> list[dict]:
    """Groups providers registered at the same normalised address. Medical office buildings make
    two providers at one address unremarkable, so groups start at three."""
    groups: dict[str, list[str]] = defaultdict(list)
    for provider_id, address in addresses.items():
        key = normalize_address(address)
        if key:
            groups[key].append(provider_id)
    return [{"address": key, "providers": sorted(ids)} for key, ids in groups.items() if len(ids) >= min_providers]


def shared_address_count(addresses: dict[str, str | None], provider_id: str) -> int:
    key = normalize_address(addresses.get(provider_id))
    if not key:
        return 0
    return sum(1 for pid, a in addresses.items() if pid != provider_id and normalize_address(a) == key)
