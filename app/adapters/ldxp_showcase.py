"""LDXP INDEX（kawanghub.com）：LDXP / 微店云铺 店铺收录站，公开 JSON 接口 /api/items（robots 允许）。"""
from .. import config
from ..net import client
from ..schema import Offer, guess_category
from ._util import polite_sleep, page_window, page_advance

BASE = "https://kawanghub.com"

def parse(data):
    for it in data.get("items") or []:
        if it.get("price") is None: continue
        sc = it.get("stockCount")
        yield Offer(source="ldxp-showcase", product=(it.get("name") or "")[:120],
                    category=guess_category(f'{it.get("group") or ""} {it.get("category") or ""} {it.get("name") or ""}'),
                    title=it.get("name") or "", price=float(it["price"]), currency="CNY",
                    seller=it.get("shopName"), url=it.get("itemUrl"), in_stock=sc is None or sc > 0, stock=sc,
                    tags=[x for x in (it.get("group"), it.get("category")) if x],
                    extra={"shop_id": it.get("shopId"), "shop_url": it.get("shopUrl"), "sales": it.get("salesCount")})

class LdxpShowcase:
    id, use_proxy, use_browser = "ldxp-showcase", False, False
    raw = None
    partial = True
    def fetch(self):
        out, raw = [], []
        with client(self.use_proxy) as c:
            total, last, done = None, 1, False
            for p in page_window("ldxp-showcase", config.LDXP_SHOWCASE_PAGES):
                if total and p > total: break
                r = c.get(BASE + "/api/items", params={"page": p, "pageSize": 100, "sort": "sales"}); r.raise_for_status()
                d = r.json(); got = list(parse(d)); out += got; raw.append({"page": p, "total": d.get("total"), "n": len(got)}); last = p
                if d.get("total"): total = -(-int(d["total"]) // 100)
                if len(got) < 100: done = True; break
                polite_sleep()
            page_advance("ldxp-showcase", last, total, done)
        self.raw = {"pages": raw}
        return out
