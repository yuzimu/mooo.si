"""从聚合站提取目标：已抓到的报价链接（priceai / aigood / apinav cards / kawanghub）、ApiNav 中转目录、kawanghub 店铺列表。"""
from .. import config, store
from ..net import client
from ..adapters._util import nuxt_payload, polite_sleep

class FromOffers:
    """复用 offers 集合里各聚合源的商品链接 → 卡网店铺 / 中转站目标。"""
    id, enabled = "offers", True
    def discover(self):
        for o in store.db().offers.find({"source": {"$in": ["priceai", "aigood", "apinav", "ldxp-showcase"]}},
                                        {"url": 1, "seller": 1, "extra": 1, "category": 1, "fetched_at": 1, "source": 1}):
            hint = "relay" if o.get("category") == "api-relay" and o.get("source") == "apinav" else "card_shop"
            for u in (o.get("url"), (o.get("extra") or {}).get("shop_url")):
                if u: yield u, hint, o.get("seller") or "", o.get("fetched_at")

class ApiNavSites:
    id, enabled, min_interval_h = "apinav-sites", True, 12
    def discover(self):
        with client(headers={"User-Agent": config.BROWSER_UA}) as c:
            for p in range(1, 12):
                r = c.get("https://apinav.cc/sites", params={"page": p} if p > 1 else None)
                if r.status_code != 200: break
                data = nuxt_payload(r.text).get("data") or {}
                items = next((v["items"] for k, v in data.items() if k.startswith("sites:") and isinstance(v, dict)), [])
                if not items: break
                for s in items:
                    if s.get("targetUrl"): yield s["targetUrl"], "relay", s.get("name") or "", None
                polite_sleep()

class KawangShops:
    id, enabled, min_interval_h = "kawanghub-shops", True, 12
    def discover(self):
        with client() as c:
            for p in range(1, 200):
                r = c.get("https://kawanghub.com/api/shops", params={"page": p, "pageSize": 50})
                if r.status_code != 200: break
                shops = r.json().get("shops") or []
                for s in shops:
                    name = s.get("shopName") or ""
                    if s.get("shopUrl"): yield s["shopUrl"], "card_shop", name, s.get("updatedAt")
                    if s.get("telegramUrl"): yield s["telegramUrl"], "tg", name, s.get("updatedAt")
                if not shops or p * len(shops) >= (r.json().get("total") or 0): break
                polite_sleep()
