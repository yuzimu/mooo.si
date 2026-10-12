"""统一搜索：卡网商品 / 卡网店铺 / 中转站 / 中转模型家族 / TG / 聚合来源，分组返回（各组独立分页）。
卡网与中转在展示上仍分组隔离（商品组永不含中转模型价）。中文分词沿用 store.tokens（双字 + 英文前缀）。"""
import re
from . import store
from .store import query_tokens, tokens

GROUPS = [("offers", "卡网商品"), ("shops", "卡网店铺"), ("relays", "中转站"), ("models", "模型价格"),
          ("tg", "TG 群组/频道"), ("sources", "聚合来源")]
TARGET_TYPE = {"shops": "card_shop", "relays": "relay", "tg": "tg"}


def index_targets(limit=50000):
    """给 targets 写入 kw 关键词数组（域名、名称、样例、平台），供 $all 查询走索引。"""
    col = store.db().targets; n = 0
    col.create_index([("kw", 1), ("type", 1)])
    for t in col.find({"kw": {"$exists": False}}, {"_id": 1, "name": 1, "url": 1, "platform": 1, "sample": 1}).limit(limit):
        text = " ".join(str(x or "") for x in (t["_id"].split(":", 1)[-1], t.get("name"), t.get("platform"), t.get("sample"),
                                                re.sub(r"[./:-]", " ", t.get("url") or "")))
        col.update_one({"_id": t["_id"]}, {"$set": {"kw": sorted(tokens(text))[:300]}}); n += 1
    return n


def _target_filter(kind, q):
    qt = query_tokens(q)
    f = {"type": TARGET_TYPE[kind], "status": {"$ne": "ignored"}}
    rx = re.escape(q.strip().lower())
    f["$or"] = [{"kw": {"$all": qt}}] if qt else []
    f["$or"] += [{"_id": {"$regex": rx}}, {"name": {"$regex": rx, "$options": "i"}}]
    return f


def _sources(q):
    from .adapters import ALL
    from .discovery import all_sources
    ql = q.lower(); out = []
    counts = {d["_id"]: d["n"] for d in store.db().offers.aggregate([{"$group": {"_id": "$source", "n": {"$sum": 1}}}])}
    for a in ALL:
        aid = getattr(a, "id", type(a).__name__); label = getattr(a, "label", None) or getattr(a, "name", None) or aid
        if ql in f"{aid} {label}".lower():
            out.append({"id": aid, "label": label, "kind": "报价聚合", "offers": counts.get(aid, 0),
                        "enabled": getattr(a, "enabled", True)})
    for s in all_sources():
        sid = getattr(s, "id", type(s).__name__)
        if ql in sid.lower(): out.append({"id": sid, "label": sid, "kind": "发现渠道", "offers": None, "enabled": s.enabled})
    return out


def search(q: str, group: str | None = None, page: int = 1, per: int = 20, preview: int = 5):
    """group=None：每组返回 preview 条 + 总数；指定 group：该组第 page 页（per 条）。"""
    q = (q or "").strip()
    res = {}
    if not q: return {g: {"label": lab, "total": 0, "items": [], "page": 1, "pages": 1} for g, lab in GROUPS}
    want = [group] if group else [g for g, _ in GROUPS]
    n = per if group else preview; skip = (max(page, 1) - 1) * n if group else 0
    for g in [g for g, _ in GROUPS]:
        lab = dict(GROUPS)[g]
        if g == "offers":
            f = store.build_filter(q=q)   # 默认剔除中转模型价（硬隔离）
            total = store.db().offers.count_documents(f)
            items = []
            if g in want:   # 相关性：标题直接含关键词的优先，其次 kw 命中（如卖家名），组内按价格
                rx = {"$regex": re.escape(q), "$options": "i"}
                f1 = {**f, "title": rx}; n1 = store.db().offers.count_documents(f1)
                col = store.db().offers
                items = [store._ns(d) for d in col.find(f1, {"kw": 0}).sort([("price", 1)]).skip(skip).limit(n)]
                if len(items) < n:
                    rest = col.find({**f, "title": {"$not": re.compile(re.escape(q), re.I)}}, {"kw": 0}).sort([("price", 1)])
                    items += [store._ns(d) for d in rest.skip(max(0, skip - n1)).limit(n - len(items))]
        elif g in TARGET_TYPE:
            f = _target_filter(g, q); col = store.db().targets
            total = col.count_documents(f)
            items = list(col.find(f, {"kw": 0}).sort([("priority", -1), ("mentions", -1)]).skip(skip).limit(n)) if g in want else []
        elif g == "models":
            from .main import _relay_rows
            from .models_tax import group_models
            rx = re.compile(re.escape(q), re.I)
            fams = [f for b in group_models(_relay_rows(lambda nm, b, fm, rx=rx: rx.search(nm) or rx.search(fm))) for f in b["families"]]
            fams.sort(key=lambda f: -f["sites"])
            total = len(fams); items = fams[skip:skip + n] if g in want else []
        else:
            allsrc = _sources(q); total = len(allsrc); items = allsrc[skip:skip + n] if g in want else []
        res[g] = {"label": lab, "total": total, "items": items, "page": page if group == g else 1,
                  "pages": max(1, -(-total // (per if group else preview)))}
    return res
