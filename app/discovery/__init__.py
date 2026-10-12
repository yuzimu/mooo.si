"""阶段一：发现。每个 DiscoverySource 产出 (url, type_hint, context, seen_at) 提及记录。"""
from typing import Iterable, Protocol

class DiscoverySource(Protocol):
    id: str
    enabled: bool
    def discover(self) -> Iterable[tuple]: ...

def all_sources():
    from .aggregators import FromOffers, ApiNavSites, KawangShops
    from .telegram import TelegramDB, TelegramPreview
    from .github import GitHubLists
    from .search import SearchEngine
    return [FromOffers(), ApiNavSites(), KawangShops(), TelegramDB(), TelegramPreview(), GitHubLists(), SearchEngine()]
