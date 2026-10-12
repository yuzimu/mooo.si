"""CATFK 店铺（与链动小铺同一套 shopApi，但 CATFK 无 ESA 验证）：Shop/goodsList（公开，店铺页前端调用）。"""
from .. import config
from ..schema import Offer, guess_category

API = "https://catfk.com/shopApi/Shop"
TYPES = ["card", "article", "resource", "equity"]

def resolve_item(c, slug):
    r = c.post(f"{API}/goodsInfo", json={"goods_key": slug}); d = r.json()
    if d.get("code") != 1: return None
    u = (d.get("data") or {}).get("user") or {}
    return u.get("token"), u.get("nickname")

def parse(data, shop_name=None):
    for g in (data.get("data") or {}).get("list") or []:
        ext = g.get("extend") or {}
        stock = ext.get("stock_count")
        name = g.get("name") or ""
        cat = (g.get("category") or {}).get("name") or ""
        yield Offer(source="catfk", product=name[:120], category=guess_category(f"{cat} {name}"), title=name,
                    price=float(g.get("price") or 0), currency="CNY",
                    seller=((g.get("user") or {}).get("nickname")) or shop_name, url=g.get("link"),
                    in_stock=stock is None or stock > 0, stock=stock, tags=[t for t in (cat, g.get("goods_type")) if t],
                    extra={"goods_key": g.get("goods_key"), "shop": (g.get("user") or {}).get("token")})

class CatFK:
    def crawl(self, c, t, sleep):
        token = t["_id"].split(":", 1)[1]
        out = []; pages = 0
        for gt in TYPES:
            for page in range(1, 20):
                if pages >= config.MAX_PAGES_PER_TARGET: break
                pages += 1
                r = c.post(f"{API}/goodsList", json={"token": token, "keywords": "", "category_id": 0, "goods_type": gt,
                                                     "current": page, "pageSize": 50})
                d = r.json()
                if d.get("code") != 1: break
                got = list(parse(d)); out += got
                if len(got) < 50: break
                sleep()
            sleep()
        return out, {"goods": len(out), "pages": pages}
