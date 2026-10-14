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

def slugify(key: str) -> str:
    """catfk:yimeng -> catfk-yimeng；web:api.foo.com -> api-foo-com；tg:name -> name"""
    k = key.split(":", 1)[1] if key.startswith(("web:", "tg:")) else key
    return re.sub(r"[^a-z0-9-]+", "-", k.lower().replace(":", "-").replace(".", "-")).strip("-")

# —— 剔除规则：通用 AI 产品 / SaaS / 官网 / 文档 / 无关站点，不是卡网店铺、中转或 TG ——
DENY_PRODUCT = {
    # AI 产品与大厂官网
    "openai.com", "chatgpt.com", "anthropic.com", "claude.ai", "gemini.google.com", "deepmind.google", "x.ai", "grok.com",
    "meta.ai", "huggingface.co", "deepseek.com", "moonshot.cn", "kimi.com", "doubao.com", "chatglm.cn", "zhipuai.cn", "bigmodel.cn",
    "tongyi.aliyun.com", "aliyun.com", "xfyun.cn", "kunlun.com", "baidu.com", "yiyan.baidu.com", "minimaxi.com", "perplexity.ai",
    "poe.com", "character.ai", "heypi.com", "inflection.ai", "mistral.ai", "cohere.com", "together.ai", "groq.com", "replicate.com",
    "midjourney.com", "stability.ai", "runwayml.com", "pika.art", "suno.com", "elevenlabs.io", "leonardo.ai", "firefly.adobe.com",
    "adobe.com", "notion.so", "jasper.ai", "copy.ai", "writesonic.com", "grammarly.com", "deepl.com", "canva.com",
    # 编程工具 / SaaS
    "cursor.so", "cursor.com", "codeium.com", "windsurf.com", "devin.ai", "codium.ai", "qodo.ai", "bito.ai", "tabnine.com",
    "github.dev", "githubcopilot.com", "replit.com", "vercel.com", "v0.dev", "bolt.new", "lovable.dev",
    "chatdoc.com", "chatpdf.com", "humata.ai", "chatbase.co", "heck.ai", "truthgpt.one", "open-assistant.io", "lmsys.org",
    "lmarena.ai", "deeplearning.ai", "coursera.org", "kaggle.com",
    # 搜索 / 统计徽章 / 文档 / 无关
    "duckduckgo.com", "bing.com", "star-history.com", "contrib.rocks", "shields.io", "readthedocs.io", "gitbook.io",
    "medium.com", "zhihu.com", "csdn.net", "juejin.cn", "bilibili.com", "nordaccount.com", "nordvpn.com",
    "wikipedia.org", "arxiv.org", "discord.com", "discord.gg", "reddit.com", "npmjs.com", "pypi.org", "docker.com",
}
KEEP_PLATFORMS = {"ldxp", "catfk", "dujiaoka", "acg-faka", "new-api", "one-api", "telegram"}

def _denied(host: str) -> bool:
    h = (host or "").lower().removeprefix("www.")
    return h in DENY_PRODUCT or any(h.endswith("." + d) for d in DENY_PRODUCT)

def ignore_reason(t: dict) -> str | None:
    """返回剔除原因；None 表示保留（店铺/中转/TG 或尚待指纹判定）。"""
    from urllib.parse import urlsplit
    host = urlsplit(t.get("url") or "").hostname or t.get("_id", "").split(":", 1)[-1]
    if (t.get("type") == "tg" or t.get("platform") in KEEP_PLATFORMS) and not _denied(host): return None
    if _denied(host): return "AI 产品/官网/通用站点，非店铺或中转"
    srcs = set((t.get("sources") or {}).keys())
    if t.get("type") == "unknown" and srcs and srcs <= {"github-lists"}:
        return "仅来自 awesome list 的通用 AI 工具，非店铺或中转"
    fp = t.get("fp") or {}
    if t.get("type") == "unknown" and t.get("fp_at") and not fp.get("platform") \
            and t.get("status") not in ("blocked_captcha", "blocked_cf", "down", "error"):
        return "指纹无发卡/中转特征（非店铺、非 new-api/one-api）"
    return None

def purge():
    """把命中剔除规则的目标标记 ignored（保留记录、注明原因、不再调度），并隐藏其报价。返回新剔除数。"""
    col = store.db().targets; n = 0
    for t in col.find({"status": {"$ne": "ignored"}, "platform": {"$nin": ["ldxp", "telegram"]}},
                      {"url": 1, "type": 1, "platform": 1, "sources": 1, "fp": 1, "fp_at": 1, "status": 1}):
        r = ignore_reason(t)
        if r:
            col.update_one({"_id": t["_id"]}, {"$set": {"status": "ignored", "ignore_reason": r, "ignored_at": now()}}); n += 1
    ign = [t["_id"] for t in col.find({"status": "ignored"}, {"_id": 1})]
    hosts = [i.split(":", 1)[1] for i in ign if i.startswith("web:")]
    off = store.db().offers
    off.update_many({"ignored": True}, {"$unset": {"ignored": 1}})
    if ign:
        off.update_many({"target": {"$in": ign}}, {"$set": {"ignored": True}})
        rx = "^https?://(www\\.)?(" + "|".join(re.escape(h) for h in hosts) + ")(?:[:/]|$)" if hosts else None
        if rx: off.update_many({"url": {"$regex": rx}, "source": {"$nin": ["apinav", "priceai", "aigood", "ldxp-showcase"]}}, {"$set": {"ignored": True}})
    return n

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
    dead = {x["_id"] for x in store.db().tombstones.find({"_id": {"$in": list(agg)}}, {"_id": 1})}
    for key, a in agg.items():
        if key in dead: continue   # 已因不可达删除的中转，不再自动加回
        ins = {"first_seen": a["seen"], "status": "new", "health": {}, "platform": a["platform"], "type": a["type"]}
        if _denied(urlsplit(a["url"]).hostname):   # 黑名单域名：即便被重新发现也只以 ignored 记录，永不调度
            ins.update(status="ignored", ignore_reason="AI 产品/官网/通用站点，非店铺或中转")
        upd = {"$setOnInsert": ins,
               "$set": {"url": a["url"], "last_seen": ts, "slug": slugify(key), f"sources.{source}": a["count"], "sample": (a["ctx"] or "")[:300]},
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
    col.create_index([("slug", 1), ("type", 1)])
    for d in col.find({"slug": {"$exists": False}}, {"_id": 1}):
        col.update_one({"_id": d["_id"]}, {"$set": {"slug": slugify(d["_id"])}})

# 公开视图只有两种状态：正常 / 下架。
#   - 下架：确认已下架（item_gone）
#   - 正常：其余一切「在收录里」的目标。抓取失败、不可达、未知平台、滑块、CF 盾、
#     待识别……全是**我们自己的管线状态**，不是店铺下架的证据，一律折叠成「正常」，
#     既不显示这些词，也不因为一次抓取失败就把店铺从目录里摘掉。
#   - ignored：我们主动不要的目标（不是店铺、已剔除），整个不进公开视图。
PUBLIC_STATUSES = ("ok", "gone")
PUBLIC_LABEL = {"ok": "正常", "gone": "下架"}
PUBLIC_GONE = ("item_gone",)
PUBLIC_HIDDEN = ("ignored",)


def public_status(st):
    """内部状态 → 公开状态（ok / gone）；整个不公开的返回 None。"""
    if st in PUBLIC_HIDDEN:
        return None
    return "gone" if st in PUBLIC_GONE else "ok"


def _public_filter(status=None):
    """公开视图的状态过滤：没指定就取全部公开目标，指定了只取该类。"""
    if status == "gone":
        return {"$in": list(PUBLIC_GONE)}
    if status == "ok":
        return {"$nin": list(PUBLIC_GONE) + list(PUBLIC_HIDDEN)}
    return {"$nin": list(PUBLIC_HIDDEN)}


def public_status_counts(**match):
    """公开视图的状态计数：{ok: n, gone: n}，内部状态不外泄。"""
    col = store.db().targets
    return {k: col.count_documents({**match, "status": _public_filter(k)}) for k in PUBLIC_STATUSES}


def search(type=None, q=None, platform=None, status=None, limit=60, skip=0, public=False):
    f = {}
    if type: f["type"] = type
    if platform: f["platform"] = platform
    if public: f["status"] = _public_filter(status)
    elif status: f["status"] = status
    else: f["status"] = {"$ne": "ignored"}   # 已剔除目标默认不展示
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


KNOWN_EXTRA_HOSTS = {"github.com", "t.me"}

def host_allowed(host: str) -> bool:
    """/go 跳转白名单：只允许本站收录过的目标域名或报价链接域名（防开放重定向）。"""
    h = (host or "").lower().removeprefix("www.")
    if not h: return False
    if h in KNOWN_EXTRA_HOSTS or h in CARD_HOSTS: return True
    d = store.db()
    if d.targets.find_one({"_id": f"web:{h}"}, {"_id": 1}): return True
    rx = {"$regex": f"^https?://(www\\.)?{re.escape(h)}(?:[:/]|$)"}
    return bool(d.offers.find_one({"url": rx}, {"_id": 1}) or d.targets.find_one({"url": rx}, {"_id": 1}))
