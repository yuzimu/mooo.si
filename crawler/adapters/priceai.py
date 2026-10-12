"""priceai.cc 官方公开 Price Radar feed（不爬 HTML / 内部 /api）。"""
import json, urllib.request
from ..schema import Offer, guess_category

LATEST = "https://data.priceai.cc/latest.json"
UA = "mooo.si-aggregator/0.1 (+https://mooo.si)"

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def parse(snapshot: dict):
    for p in snapshot.get("products", []):
        cat = guess_category(f'{p.get("platform","")} {p.get("name","")}')
        for o in p.get("top_offers") or []:
            yield Offer(source="priceai", product=p.get("name"), category=cat,
                        title=o.get("title") or "", price=float(o.get("price") or 0),
                        currency=o.get("currency") or "CNY", seller=o.get("source_name"),
                        url=o.get("url"), in_stock=o.get("status") == "in_stock",
                        stock=o.get("stock_count"), captured_at=o.get("captured_at"),
                        tags=[p.get("product_type") or "", p.get("spec") or ""])

class PriceAI:
    id = "priceai"
    def fetch(self):
        return list(parse(_get(_get(LATEST)["snapshot_url"])))
