"""new-api / one-api 中转站：/api/pricing（公开定价页数据）。
价格换算：倍率 1 ≈ $2 / 1M tokens（输入）；实际价格 = model_ratio × 最低可用分组倍率 × 2 USD/1M；
按次计费（quota_type=1）取 model_price × group_ratio → $/次（生图/视频等多为此模式）。
完整字段写入 relay_prices，重点文本模型 + 全部生图模型写入 offers。"""
import re
from .. import config, store
from ..schema import Offer

IMAGE_RE = re.compile(
    r"image|dall-?e|flux|midjourney|seedream|jimeng|kling|banana|imagen|veo|imagine|"
    r"stable-?diffusion|sdxl|ideogram|recraft|luma|runway|sora|cogview|wanx|kolors", re.I)

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
        mr = m.get("model_ratio"); mp = m.get("model_price"); cr = m.get("completion_ratio")
        qt = m.get("quota_type")  # 1=按次, 0/None=按量
        if qt == 1 or (mp and not mr):
            price = round(float(mp or 0) * ratio, 6); unit = "次"
        else:
            price = round(float(mr or 0) * 2 * ratio, 6); unit = "1M tokens"
        is_image = bool(IMAGE_RE.search(name))
        rows.append({"model": name, "price": price, "unit": unit, "group_ratio": ratio,
                     "model_ratio": mr, "model_price": mp, "completion_ratio": cr, "quota_type": qt,
                     "groups": groups[:10], "is_image": is_image})
        if price > 0 and (featured.search(name) or is_image):
            cat = "nano-banana-api" if is_image else "api-relay"
            yield Offer(source="relay", product=f"{name} @ {site}", category=cat,
                        title=f"{name} · ${price}/{unit}", price=price, currency="USD", seller=site, url=url,
                        in_stock=True, tags=[unit, "new-api"] + (["image"] if is_image else []),
                        extra={"model": name, "unit": unit, "group_ratio": ratio, "model_ratio": mr,
                               "model_price": mp, "completion_ratio": cr, "quota_type": qt, "is_image": is_image})
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
        cur = None
        try:
            sleep()
            rs = c.get(base + "/api/status", timeout=15)
            if rs.status_code == 200:
                from ..models_tax import rate_info
                cur = rate_info((rs.json() or {}).get("data") or {})
        except Exception:  # noqa: BLE001
            cur = None
        doc = {"_id": t["_id"], "site": site, "url": base, "models": rows, "updated_at": store.now()}
        if cur: doc["currency"] = cur
        else:
            old = store.db().relay_prices.find_one({"_id": t["_id"]}, {"currency": 1}) or {}
            if old.get("currency"): doc["currency"] = old["currency"]
        store.db().relay_prices.replace_one({"_id": t["_id"]}, doc, upsert=True)
        return offers, {"models": len(rows), "image_models": sum(1 for x in rows if x.get("is_image"))}
