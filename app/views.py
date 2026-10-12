"""页面视图数据组装与模板过滤器。"""
from collections import defaultdict
from datetime import datetime, timezone
from .schema import CATEGORIES

SYMBOL = {"CNY": "¥", "USD": "$", "USDT": "₮", "EUR": "€"}

def money(v, cur="CNY"):
    if v is None: return "—"
    if v == 0: return "免费/面议"
    s = f"{v:,.2f}" if v < 1000 else f"{v:,.0f}"
    if v < 1: s = f"{v:.2f}".rstrip("0").rstrip(".") if v >= 0.01 else f"{v:.3f}"
    return f"{SYMBOL.get(cur, cur + ' ')}{s}"

def _dt(v):
    if v is None: return None
    if isinstance(v, datetime): d = v
    else:
        try: d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError: return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def reltime(v):
    d = _dt(v)
    if not d: return "—"
    s = (datetime.now(timezone.utc) - d).total_seconds()
    if s < 60: return "刚刚"
    if s < 3600: return f"{int(s // 60)} 分钟前"
    if s < 86400: return f"{int(s // 3600)} 小时前"
    return f"{int(s // 86400)} 天前"

def cat_meta(c):
    label, icon, section = CATEGORIES.get(c, CATEGORIES["other"])
    return {"id": c, "label": label, "icon": icon, "section": section}

def group_products(offers, sort="featured"):
    g = defaultdict(list)
    for o in offers: g[o.product].append(o)
    groups = []
    for name, items in g.items():
        items.sort(key=lambda o: (not o.in_stock, o.price))
        prices = [o.price for o in items]
        groups.append({"name": name, "category": items[0].category, "tags": items[0].tags or [],
                       "offers": items, "min": min(prices), "max": max(prices),
                       "currency": items[0].currency, "in_stock": sum(1 for o in items if o.in_stock),
                       "updated": max((o.fetched_at for o in items), default=None)})
    order = list(CATEGORIES)
    key = {"featured": lambda x: (order.index(x["category"]) if x["category"] in order else 99, x["min"]),
           "price": lambda x: x["min"], "-price": lambda x: -x["min"],
           "sellers": lambda x: -len(x["offers"]), "name": lambda x: x["name"]}.get(sort, lambda x: (0, x["min"]))
    return sorted(groups, key=key)

def category_cards(all_offers):
    acc = {}
    for o in all_offers:
        a = acc.setdefault(o.category, {"min": None, "products": set(), "count": 0, "cur": o.currency})
        a["count"] += 1; a["products"].add(o.product)
        if o.in_stock and o.price > 0 and (a["min"] is None or o.price < a["min"]): a["min"] = o.price
    out = [{**cat_meta(c), "min": v["min"], "cur": v["cur"], "products": len(v["products"]), "count": v["count"]}
           for c, v in acc.items()]
    return sorted(out, key=lambda x: (x["id"] == "other", -x["count"]))

def cheapest(all_offers, n=8, floor=1.0):
    """今日低价：每个商品的有货最低价，按「比同款均价低多少」排序，忽略 floor 以下的边角料。"""
    by = defaultdict(list)
    for o in all_offers:
        if o.in_stock and o.price > 0: by[o.product].append(o)
    picks = []
    for items in by.values():
        best = min(items, key=lambda o: o.price)
        if best.price < floor or len(items) < 2: continue
        avg = sum(o.price for o in items) / len(items)
        best.save_pct = round((1 - best.price / avg) * 100) if avg else 0
        best.avg = avg
        picks.append(best)
    return sorted(picks, key=lambda o: -o.save_pct)[:n]
