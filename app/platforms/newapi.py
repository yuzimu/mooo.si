"""new-api / one-api 中转站：/api/pricing（公开定价页数据）。
价格换算：倍率 1 ≈ $2 / 1M tokens（输入）；实际价格 = model_ratio × 最低可用分组倍率 × 2 USD/1M；按次计费模型取 model_price。
只把重点模型（RELAY_FEATURED）写入 offers，完整定价表存 relay_prices。"""
import re
from .. import config, store
from ..schema import Offer

def _groups(d):
    g = d.get("group_ratio") or {}
    return g if isinstance(g, dict) else {}

def parse(d, site, url):
    featured = re.compile(config.RELAY_FEATURED, re.I)
    gr = _groups(d); rows = []
    for m in d.get("data") or []:
        name = m.get("model_name") or ""
        groups = m.get("enable_groups") or list(gr) or ["default"]
        ratio = min([gr.get(x, 1) for x in groups if isinstance(gr.get(x, 1), (int, float))] or [1])
        if m.get("quota_type") == 1:
            price, unit = round((m.get("model_price") or 0) * ratio, 4), "次"
        else:
            price, unit = round((m.get("model_ratio") or 0) * 2 * ratio, 4), "1M tokens"
        rows.append({"model": name, "price": price, "unit": unit, "group_ratio": ratio,
                     "completion_ratio": m.get("completion_ratio"), "groups": groups[:10]})
        if featured.search(name) and price > 0:
            yield Offer(source="relay", product=f"{name} @ {site}", category="nano-banana-api" if "banana" in name.lower() else "api-relay",
                        title=f"{name} · ${price}/{unit}", price=price, currency="USD", seller=site, url=url, in_stock=True,
                        tags=[unit, "new-api"], extra={"model": name, "unit": unit, "group_ratio": ratio})
    parse.rows = rows

class NewAPI:
    def crawl(self, c, t, sleep):
        base = t["url"].rstrip("/")
        r = c.get(base + "/api/pricing", timeout=20)
        if r.status_code != 200: raise RuntimeError(f"/api/pricing HTTP {r.status_code}")
        if r.extensions.get("not_modified"): return None, {"unchanged": True}
        d = r.json()
        if not d.get("success", True) or not isinstance(d.get("data"), list): raise RuntimeError("pricing 需登录或不公开")
        site = t.get("name") or t["_id"].split(":", 1)[1]
        offers = list(parse(d, site, base))
        rows = getattr(parse, "rows", [])
        store.db().relay_prices.replace_one({"_id": t["_id"]}, {"_id": t["_id"], "site": site, "url": base, "models": rows,
                                                                "updated_at": store.now()}, upsert=True)
        return offers, {"models": len(rows)}
