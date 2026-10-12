"""目标（监控对象）规范化与存储：中转站 relay / 卡网店铺 card_shop / TG 群组频道 tg。"""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from . import store

def now(): return datetime.now(timezone.utc)

# 不是目标的常见域名
IGNORE = {"github.com", "raw.githubusercontent.com", "google.com", "youtube.com", "x.com", "twitter.com", "qq.com",
          "bilibili.com", "zhihu.com", "weixin.qq.com", "mp.weixin.qq.com", "openai.com", "chatgpt.com", "claude.ai",
          "anthropic.com", "gemini.google.com", "grok.com", "baidu.com", "apple.com", "microsoft.com", "wikipedia.org",
          "linux.do", "invite.linuxdo.org", "nav.linux.do", "android.linux.do", "telegram.org", "telegra.ph",
          "cdn.jsdelivr.net", "img.shields.io", "outlook.jp", "outlook.de",
          "outlook.com", "gmail.com", "now.com", "poe.com", "aigood.chat", "apinav.cc", "priceai.cc", "kawanghub.com",
          "assets.apinav.cc", "static.catfk.com", "muse.ai",
          "bjtu.edu.cn", "open.boc.cn", "aaaaa.com", "example.com", "readdy.co"}
CARD_HOSTS = {"catfk.com": "catfk", "pay.ldxp.cn": "ldxp", "www.ldxp.cn": "ldxp", "ldxp.cn": "ldxp", "wzyp.cn": "ldxp"}

def _host(u):
    if "://" not in u: u = "https://" + u
    s = urlsplit(u)
    return (s.hostname or "").lower().removeprefix("www."), s.path or "/"

def classify(url: str, hint: str | None = None):
    """返回 dict(key, type, platform, url, ref) 或 None。ref 记录原始的商品/消息路径。"""
    url = url.strip().rstrip(".,;:!?)）】」'\"")
    host, path = _host(url)
    if not host or "." not in host: return None
    if host in ("t.me", "telegram.me"):
        m = re.match(r"^/(?:s/)?([A-Za-z][\w]{3,})", path)
        if not m or m.group(1).lower() in ("joinchat", "c", "share", "addstickers", "proxy", "iv"): return None
        name = m.group(1)
        return {"key": f"tg:{name.lower()}", "type": "tg", "platform": "telegram", "url": f"https://t.me/{name}", "ref": url}
    if host in IGNORE or any(host.endswith("." + d) for d in IGNORE if d.count(".") == 1): return None
    if host.endswith((".gov.cn", ".edu.cn")): return None
    plat = CARD_HOSTS.get(host) or CARD_HOSTS.get("www." + host)
    if plat:
        m = re.match(r"^/(shop|item|s)/([\w-]+)", path)
        if not m: return None
        kind, slug = m.group(1), m.group(2)
        if kind == "item":  # 商品链接：先以商品为键，抓取阶段解析出店铺后合并
            return {"key": f"{plat}:item:{slug}", "type": "card_shop", "platform": plat, "url": f"https://{host}/item/{slug}",
                    "ref": url, "pending_item": slug}
        return {"key": f"{plat}:{slug.lower()}", "type": "card_shop", "platform": plat, "url": f"https://{host}/shop/{slug}", "ref": url}
    t = hint or "unknown"
    return {"key": f"web:{host}", "type": t, "platform": None, "url": f"https://{host}/", "ref": url}

def upsert(mentions, source: str):
    """mentions: iterable of (url, hint, context, seen_at)。按 key 合并计数。"""
    col = store.db().targets; n = 0; ts = now()
    agg = {}
    for url, hint, ctx, seen in mentions:
        c = classify(url, hint)
        if not c: continue
        a = agg.setdefault(c["key"], {**c, "count": 0, "ctx": ctx, "seen": seen or ts})
        a["count"] += 1
        if hint and a["type"] == "unknown": a["type"] = hint
    for key, a in agg.items():
        ins = {"first_seen": a["seen"], "status": "new", "health": {}, "platform": a["platform"], "type": a["type"]}
        upd = {"$setOnInsert": ins,
               "$set": {"url": a["url"], "last_seen": ts, f"sources.{source}": a["count"], "sample": (a["ctx"] or "")[:300]},
               "$inc": {"mentions": a["count"]}, "$addToSet": {"refs": {"$each": [a["ref"]][:1]}}}
        if a.get("pending_item"): upd["$set"]["pending_item"] = a["pending_item"]
        if a["type"] == "relay" and a["platform"] is None:  # 中转提示优先于卡网/未知
            ins.pop("type"); upd["$set"]["type"] = "relay"
        col.update_one({"_id": key}, upd, upsert=True); n += 1
    return n

def ensure_indexes():
    col = store.db().targets
    col.create_index([("type", 1), ("status", 1), ("mentions", -1)])
    col.create_index([("platform", 1)])
    col.create_index([("kw", 1)])
    col.create_index([("last_seen", -1)])

def search(type=None, q=None, platform=None, status=None, limit=60, skip=0):
    f = {}
    if type: f["type"] = type
    if platform: f["platform"] = platform
    if status: f["status"] = status
    if q: f["$or"] = [{"_id": {"$regex": re.escape(q.lower())}}, {"name": {"$regex": re.escape(q), "$options": "i"}},
                      {"sample": {"$regex": re.escape(q), "$options": "i"}}]
    col = store.db().targets
    return list(col.find(f).sort([("priority", -1), ("mentions", -1)]).skip(skip).limit(limit)), col.count_documents(f)

def stats():
    col = store.db().targets
    by = {}
    for d in col.aggregate([{"$group": {"_id": {"t": "$type", "p": "$platform", "s": "$status"}, "n": {"$sum": 1}}}]):
        by[(d["_id"].get("t"), d["_id"].get("p"), d["_id"].get("s"))] = d["n"]
    return by
