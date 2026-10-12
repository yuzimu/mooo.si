"""priceai.cc 官方 Price Radar 公开 feed，不爬 HTML / 内部 /api。"""
from ..net import client
from ..schema import Offer, guess_category

LATEST = "https://data.priceai.cc/latest.json"

def parse(snapshot: dict):
    for p in snapshot.get("products", []):
        cat = guess_category(f'{p.get("platform", "")} {p.get("name", "")}')
        for o in p.get("top_offers") or []:
            if not o.get("price"): continue  # 跳过 0 元说明贴
            yield Offer(source="priceai", product=p.get("name") or "", category=cat,
                        title=o.get("title") or "", price=float(o.get("price") or 0),
                        currency=o.get("currency") or "CNY", seller=o.get("source_name"),
                        url=o.get("url"), in_stock=o.get("status") == "in_stock",
                        stock=o.get("stock_count"), captured_at=o.get("captured_at"),
                        tags=[t for t in (p.get("product_type"), p.get("spec")) if t],
                        extra={"product_id": p.get("id"), "offer_id": o.get("id"),
                               "min_order": o.get("min_order_quantity"), "expires_at": o.get("expires_at")})

class PriceAI:
    id, use_proxy, use_browser = "priceai", False, False
    raw = None
    def fetch(self):
        with client(self.use_proxy) as c:
            latest = c.get(LATEST).json()
            snap = c.get(latest["snapshot_url"]).json()
            self.raw = snap  # 原始快照存入 Mongo raw 集合
            return list(parse(snap))
