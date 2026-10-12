"""每日管线：聚合源抓取 → 阶段一发现 → 阶段二定向抓取 → 跨源去重。"""
import logging, math, random, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlsplit
from . import config, store, targets
from .crawler import run_all
from .discovery import all_sources
from .net import client, check_proxy, meter
from .platforms import fingerprint, CRAWLERS
from .platforms.catfk import resolve_item

log = logging.getLogger("mooo.pipeline")
DIRECT_SOURCES = ["catfk", "relay"]

def dedupe_key(url):
    if not url: return None
    s = urlsplit(url if "://" in url else "https://" + url)
    return f"{(s.hostname or '').removeprefix('www.')}{s.path.rstrip('/')}".lower()

def run_discovery():
    res = {}
    state = store.db().discovery_state
    for src in all_sources():
        if not src.enabled: res[src.id] = "disabled"; continue
        st = state.find_one({"_id": src.id}) or {}
        gap = getattr(src, "min_interval_h", 0)
        if gap and st.get("at") and store.now() - st["at"].replace(tzinfo=store.now().tzinfo) < timedelta(hours=gap):
            res[src.id] = "skipped(interval)"; continue
        try:
            res[src.id] = targets.upsert(src.discover(), src.id)
            state.replace_one({"_id": src.id}, {"_id": src.id, "at": store.now(), "n": res[src.id]}, upsert=True)
        except Exception as e:  # noqa: BLE001
            res[src.id] = f"error: {e!r}"[:300]
        log.info("discovery %s -> %s", src.id, res[src.id])
    store.db().pipeline_runs.insert_one({"stage": "discovery", "at": store.now(), "result": res})
    return res

def _merge_catfk_items(c):
    col = store.db().targets
    for t in list(col.find({"pending_item": {"$exists": True}, "platform": "catfk"}).limit(500)):
        try:
            got = resolve_item(c, t["pending_item"])
        except Exception:  # noqa: BLE001
            got = None
        if not got: col.update_one({"_id": t["_id"]}, {"$unset": {"pending_item": 1}, "$set": {"status": "item_gone"}}); continue
        token, nick = got; key = f"catfk:{token.lower()}"
        col.update_one({"_id": key}, {"$setOnInsert": {"first_seen": t.get("first_seen"), "type": "card_shop", "platform": "catfk",
                                                        "url": f"https://catfk.com/shop/{token}", "status": "new", "health": {}},
                                      "$set": {"name": nick, "last_seen": t.get("last_seen")},
                                      "$inc": {"mentions": t.get("mentions", 1)}}, upsert=True)
        col.delete_one({"_id": t["_id"]})
        time.sleep(0.5)

def priority(t):
    age_days = 30
    if t.get("last_seen"):
        ls = t["last_seen"]
        if ls.tzinfo is None: ls = ls.replace(tzinfo=store.now().tzinfo)
        age_days = (store.now() - ls).days
    return round(math.log2(1 + t.get("mentions", 1)) * 10 + max(0, 30 - age_days) + len(t.get("sources") or {}) * 3, 2)

def _crawl_domain(items):
    """同一域名内串行 + 间隔（每域限速）；域名之间并发。"""
    out = []
    with client(headers={"User-Agent": config.BROWSER_UA}) as c:
        for t in items:
            health = {"at": store.now()}
            try:
                fp = t.get("fp") if t.get("fp_at") and store.now() - t["fp_at"].replace(tzinfo=store.now().tzinfo) < timedelta(days=7) \
                    else fingerprint(c, t)
                upd = {"fp": fp, "fp_at": store.now(), "status": fp["status"], "priority": priority(t)}
                if fp.get("platform"): upd["platform"] = fp["platform"]
                if fp.get("name") and not t.get("name"): upd["name"] = fp["name"][:80]
                if fp.get("platform") in ("new-api", "one-api") and t.get("type") == "unknown": upd["type"] = "relay"
                plat = upd.get("platform") or t.get("platform")
                crawler = CRAWLERS.get(plat)
                if fp["status"] == "ok" and crawler:
                    time.sleep(config.DOMAIN_DELAY)
                    offers, meta = crawler.crawl(c, {**t, **upd}, lambda: time.sleep(config.DOMAIN_DELAY))
                    if offers is None:  # 304 / 内容未变：保留已有报价
                        health.update(ok=True, unchanged=True, offers=(t.get("health") or {}).get("offers", 0))
                    else:
                        for o in offers: o.extra["target"] = t["_id"]
                        store.save_target_offers(t["_id"], [o.to_dict() for o in offers])
                        health.update(ok=True, offers=len(offers), **meta)
                    upd["status"] = "monitored"
                else:
                    health.update(ok=fp["status"] == "ok", skipped=fp["status"] if fp["status"] != "ok" else "no_adapter",
                                  note=fp.get("note"))
            except Exception as e:  # noqa: BLE001
                health.update(ok=False, error=repr(e)[:300]); upd = {"status": "error"}
            store.db().targets.update_one({"_id": t["_id"]}, {"$set": {**upd, "health": health},
                                                              "$push": {"history": {"$each": [health], "$slice": -10}}})
            out.append((t["_id"], health)); time.sleep(config.DOMAIN_DELAY + random.random())
    return out

def run_targeted(limit=None):
    col = store.db().targets
    with client(headers={"User-Agent": config.BROWSER_UA}) as c:
        _merge_catfk_items(c)
    # 链动小铺/微店云铺 全站 ESA 滑块：直接批量标记跳过，不占抓取配额、不发请求
    col.update_many({"platform": "ldxp"}, {"$set": {"status": "blocked_captcha", "fp": {"platform": "ldxp", "status": "blocked_captcha",
                    "note": "阿里云 ESA 滑块，跳过；商品经 kawanghub/aigood 间接覆盖"}}})
    cand = list(col.find({"type": {"$in": ["card_shop", "relay", "unknown"]}, "pending_item": {"$exists": False}, "platform": {"$ne": "ldxp"},
                          "status": {"$nin": ["item_gone"]}}))
    for t in cand: t["_prio"] = priority(t)
    cand.sort(key=lambda t: -t["_prio"])
    # 最近 TARGET_MIN_INTERVAL_H 小时内成功抓过的目标本轮跳过，把配额让给其它目标（错峰）
    fresh = store.now() - timedelta(hours=config.TARGET_MIN_INTERVAL_H)
    def recent(t):
        at = (t.get("health") or {}).get("at")
        return bool(at) and (t.get("health") or {}).get("ok") and at.replace(tzinfo=store.now().tzinfo) > fresh
    cand = [t for t in cand if not recent(t)][: limit or config.TARGET_CRAWL_MAX]
    by_domain = defaultdict(list)
    for t in cand: by_domain[urlsplit(t["url"]).hostname].append(t)
    results = []
    with ThreadPoolExecutor(config.TARGET_WORKERS) as ex:
        for r in ex.map(_crawl_domain, by_domain.values()): results += r
    dedupe()
    summary = {"targets": len(results), "ok": sum(1 for _, h in results if h.get("ok")),
               "offers": sum(h.get("offers", 0) for _, h in results)}
    store.db().pipeline_runs.insert_one({"stage": "targeted", "at": store.now(), "result": summary})
    return summary

def dedupe():
    """直连抓取（catfk/relay）优先：聚合源中链接相同的报价标记 dup=True，前台不再重复显示。"""
    off = store.db().offers
    off.update_many({}, {"$unset": {"dup": 1}})
    direct = {d["dedupe_key"] for d in off.find({"source": {"$in": DIRECT_SOURCES}, "dedupe_key": {"$ne": None}}, {"dedupe_key": 1})}
    n = off.update_many({"source": {"$nin": DIRECT_SOURCES}, "dedupe_key": {"$in": list(direct)}}, {"$set": {"dup": True}}).modified_count
    # 聚合源之间：同链接只保留最近抓到的一条
    seen = set()
    for d in off.find({"source": {"$nin": DIRECT_SOURCES}, "dup": {"$ne": True}, "dedupe_key": {"$ne": None}},
                      {"dedupe_key": 1}).sort("fetched_at", -1):
        if d["dedupe_key"] in seen: off.update_one({"_id": d["_id"]}, {"$set": {"dup": True}}); n += 1
        else: seen.add(d["dedupe_key"])
    return n

def cycle():
    """每 CRAWL_EVERY_HOURS 小时一轮。先确认代理可用（fail closed），统计本轮流量。"""
    meter.reset(); t0 = time.time()
    try:
        egress = check_proxy()
    except Exception as e:  # noqa: BLE001
        store.db().pipeline_runs.insert_one({"stage": "cycle", "at": store.now(), "error": str(e)[:500]})
        log.error("%s", e); return {"error": str(e)}
    run_all(); disc = run_discovery(); tgt = run_targeted()
    res = {"egress": egress, "discovery": disc, "targeted": tgt, "traffic": meter.snapshot(), "seconds": round(time.time() - t0)}
    store.db().pipeline_runs.insert_one({"stage": "cycle", "at": store.now(), "result": res})
    log.info("cycle done %s", {k: res[k] for k in ("egress", "targeted", "seconds")} | {"bytes": res["traffic"]["bytes"]})
    return res

daily = cycle

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    store.ensure_indexes(); targets.ensure_indexes()
    stage = sys.argv[1] if len(sys.argv) > 1 else "daily"
    print({"daily": cycle, "cycle": cycle, "discovery": run_discovery, "targeted": run_targeted, "dedupe": dedupe}[stage]())
