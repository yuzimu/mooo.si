"""ApiNav apinav.cc：Nuxt SSR 页面内嵌 __NUXT_DATA__。robots 禁止 /api/，只读公开页面。
- /sites  → API 中转站目录（起充金额、支持模型、支付方式、可用率）
- /cards  → 卡网商品聚合（价格、库存、来源店铺）"""
from .. import config
from ..net import client
from ..schema import Offer, guess_category
from ._util import nuxt_payload, polite_sleep, parse_price, page_window, page_advance

BASE = "https://apinav.cc"

def _items(payload, prefix):
    for k, v in (payload.get("data") or {}).items():
        if k.startswith(prefix) and isinstance(v, dict) and "items" in v:
            return v
    return {"items": []}

def parse_sites(payload):
    for s in _items(payload, "sites:")["items"]:
        price, cur = parse_price(s.get("topupLabel") or "")
        if price is None: price, cur = s.get("minTopupAmount") or 0, "CNY"
        up = s.get("uptime") or {}
        yield Offer(source="apinav", product=s.get("name") or "", category="api-relay",
                    title=f'{s.get("name")} · {s.get("topupLabel") or ""}'.strip(" ·"), price=float(price or 0),
                    currency=cur or "CNY", seller=s.get("name"), url=s.get("targetUrl"),
                    in_stock=bool(up.get("lastOk", True)), captured_at=up.get("checkedAt") or s.get("updatedAt"),
                    tags=(s.get("tags") or [])[:3],
                    extra={"models": s.get("supportedModels"), "payments": s.get("paymentMethods"),
                           "uptime": up.get("ratio"), "latency_ms": up.get("avgLatencyMs"), "slug": s.get("slug")})

def parse_cards(payload):
    for it in _items(payload, "card-products")["items"]:
        if it.get("price") is None: continue
        yield Offer(source="apinav", product=(it.get("name") or "")[:120],
                    category=guess_category(f'{it.get("category") or ""} {it.get("name") or ""}'),
                    title=it.get("name") or "", price=float(it["price"]), currency=it.get("currency") or "CNY",
                    seller=it.get("shopName") or it.get("sourceShop"),
                    url=it.get("detailUrl") or None,  # 无商品深链则留空，由 quality.hide_no_url 隐藏（不再用店铺首页冒充）
                    in_stock=it.get("status") == "in_stock", stock=it.get("stock"),
                    tags=[x for x in (it.get("category"), it.get("sourcePlatform")) if x],
                    extra={"origin": it.get("sourceShop"), "last_seen": it.get("lastSeenAt"),
                           "source_url": it.get("sourceUrl"), "has_detail": bool(it.get("detailUrl"))})

class ApiNav:
    id, use_proxy, use_browser = "apinav", False, False
    raw = None
    partial = True
    def fetch(self):
        out, raw = [], {"sites": [], "cards": []}
        with client(self.use_proxy, headers={"User-Agent": config.BROWSER_UA}) as c:
            for path, parser, pages, key in (("/sites", parse_sites, config.APINAV_SITE_PAGES, "sites"),
                                             ("/cards", parse_cards, config.APINAV_CARD_PAGES, "cards")):
                total, last, done = None, 1, False
                for p in page_window(f"apinav-{key}", pages):
                    if total and p > total: break
                    r = c.get(BASE + path, params={"page": p} if p > 1 else None); r.raise_for_status()
                    pl = nuxt_payload(r.text)
                    meta = _items(pl, "card-products" if key == "cards" else "sites:")
                    if meta.get("total") and meta.get("pageSize"): total = -(-int(meta["total"]) // int(meta["pageSize"]))
                    got = list(parser(pl)); out += got; raw[key].append(len(got)); last = p
                    if not got: done = True; break
                    polite_sleep()
                page_advance(f"apinav-{key}", last, total, done)
                raw[key + "_total_pages"] = total
        self.raw = raw
        return out
