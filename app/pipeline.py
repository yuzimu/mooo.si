"""每日管线：聚合源抓取 → 阶段一发现 → 阶段二定向抓取 → 跨源去重。"""
import logging, math, os, random, re, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlsplit
from . import config, store, targets
from .crawler import run_all
from .discovery import all_sources
from .net import client, check_proxy, meter
from .platforms import fingerprint, CRAWLERS
from . import quality
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

def _egress_kw(t):
    """ldxp 需要中国出口（ESA 只放行中国 IP），单独走 LDXP_PROXY_* 池；其余目标用主代理池。"""
    from .platforms import ldxp
    if not t: return {}
    if t.get("platform") == "ldxp" or str(t.get("_id", "")).startswith("ldxp:"):
        p = ldxp.cn_proxy()
        if p: return {"proxy": p}
    return {}


def _crawl_domain(items):
    """同一域名内串行 + 间隔（每域限速）；域名之间并发。"""
    out = []
    with client(headers={"User-Agent": config.BROWSER_UA}, **_egress_kw(items[0] if items else None)) as c:
        for t in items:
            heartbeat()
            if time.time() > _DEADLINE[0]:
                log.info("cycle time budget reached, defer %s", t["_id"]); break   # 时间预算用完：顺延，避免与下一轮重叠
            if meter.bytes > config.CYCLE_BYTE_BUDGET_MB * 1e6:
                log.info("byte budget reached, defer %s", t["_id"]); break   # 流量预算用完：剩余目标顺延到下一轮
            health = {"at": store.now()}
            try:
                fp = t.get("fp") if t.get("fp_at") and store.now() - t["fp_at"].replace(tzinfo=store.now().tzinfo) < timedelta(days=7) \
                    else None
                if not fp:
                    fp = fingerprint(c, t)
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
                health.update(ok=False, error=repr(e)[:300])
                # 定价接口需登录（401/403）≠ 故障：标记 private，按失败重试间隔复查
                upd = {"status": "private" if re.search(r"HTTP 40[13]|需登录", repr(e)) else "error"}
            store.db().targets.update_one({"_id": t["_id"]}, {"$set": {**upd, "health": health},
                                                              "$push": {"history": {"$each": [health], "$slice": -10}}})
            out.append((t["_id"], health)); time.sleep(config.DOMAIN_DELAY + random.random())
    return out

_DEADLINE = [float("inf")]


def _ldxp_canary(c, col):
    """抽一个 ldxp 店铺探 ShopApi：返回 JSON 才放行全部 ldxp 目标；若被 ESA/WAF 拦截则整批跳过（不绕过验证码）。

    注意「批量跳过」必须可回收：整批写 blocked_captcha 会让目标被 run_targeted 冷处理 CAPTCHA_RETRY_H 小时，
    一次探针抖动就锁死上万个目标（2026-10-12 曾把 18458 个全标成 blocked_captcha 且从此不再重试）。
    因此批量标记打 ldxp_canary_blocked，探针恢复后只复位这批；真·逐个风控的目标不受影响。
    """
    from .platforms.ldxp import probe
    t = col.find_one({"platform": "ldxp", "_id": {"$regex": "^ldxp:"}}, {"_id": 1})
    if not t: return True
    from .platforms import ldxp
    proxy = ldxp.cn_proxy()
    if proxy:
        # 探针也必须走国内出口，否则永远探不通
        with client(proxy=proxy, cache=False, headers={"User-Agent": config.BROWSER_UA}) as lc:
            ok, note = probe(lc, t["_id"].split(":", 1)[1])
    else:
        ok, note = probe(c, t["_id"].split(":", 1)[1])
    store.db().pipeline_runs.insert_one({"stage": "ldxp_canary", "at": store.now(), "ok": ok, "note": note[:200]})
    if ok:
        # 探针恢复：复位上一轮 canary 批量标记的目标，并清掉它们的 fp 以便重新指纹
        r = col.update_many({"platform": "ldxp", "ldxp_canary_blocked": True},
                            {"$set": {"status": "new"},
                             "$unset": {"ldxp_canary_blocked": 1, "fp": 1, "fp_at": 1}})
        if r.modified_count:
            store.db().pipeline_runs.insert_one({"stage": "ldxp_canary_unblock", "at": store.now(), "n": r.modified_count})
            log.info("ldxp canary recovered, unblocked %s targets", r.modified_count)
        return True
    if "风控" in note or "WAF" in note:
        # 只批量标记「从来没有成功采到过数据」的目标。已经 health.ok=True 的是真有数据的
        # （例如本地轮换出口跑完后一次性导入的），不能被探针抖动打回 blocked_captcha。
        r = col.update_many({"platform": "ldxp", "status": {"$nin": ["item_gone", "ignored"]},
                             "health.ok": {"$ne": True}},
                            {"$set": {"status": "blocked_captcha", "fp_at": store.now(), "ldxp_canary_blocked": True,
                                      "fp": {"platform": "ldxp", "status": "blocked_captcha",
                                             "note": f"ShopApi 也被阿里云 ESA/WAF 拦截，跳过（{note[:120]}）"}}})
        store.db().pipeline_runs.insert_one({"stage": "ldxp_canary_block", "at": store.now(), "n": r.modified_count})
        return False
    return True


def run_targeted(limit=None, max_minutes=None):
    col = store.db().targets
    mm = max_minutes or config.CYCLE_MAX_MINUTES
    _DEADLINE[0] = time.time() + 60 * mm if mm else float("inf")   # 默认不设时间上限：跑完为止（锁保证不重叠）
    with client(headers={"User-Agent": config.BROWSER_UA}) as c:
        _merge_catfk_items(c)
        ldxp_ok = _ldxp_canary(c, col)
    f = {"type": {"$in": ["card_shop", "relay", "unknown"]}, "pending_item": {"$exists": False},
         "status": {"$nin": ["item_gone", "ignored"]}}
    if not ldxp_ok: f["platform"] = {"$ne": "ldxp"}
    cand = list(col.find(f))
    for t in cand: t["_prio"] = priority(t)
    cand.sort(key=lambda t: -t["_prio"])
    # 最近 TARGET_MIN_INTERVAL_H 小时内成功抓过的目标本轮跳过，把配额让给其它目标（错峰）
    fresh = store.now() - timedelta(hours=config.TARGET_MIN_INTERVAL_H)
    retry = store.now() - timedelta(hours=config.FAIL_RETRY_H)
    def recent(t):
        h = t.get("health") or {}; at = h.get("at")
        if not at: return False
        at = at.replace(tzinfo=store.now().tzinfo)
        return at > (fresh if h.get("ok") else retry)   # 成功的按 MIN_INTERVAL 错峰，失败的（非验证码）按 FAIL_RETRY_H 重试
    captcha_cool = store.now() - timedelta(hours=config.CAPTCHA_RETRY_H)
    cand = [t for t in cand if not recent(t) and not (t.get("status") == "blocked_captcha" and t.get("fp_at")
                                                       and t["fp_at"].replace(tzinfo=store.now().tzinfo) > captcha_cool)]
    # 从未抓过的优先，其次按优先级（提及数/新鲜度/来源数）
    cand.sort(key=lambda t: (bool((t.get("health") or {}).get("at")), -t["_prio"]))
    if limit:
        cand = cand[:limit]
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

LEASE_MIN = 20   # 租约 20 分钟，运行中每处理一个目标续租；进程崩溃后 20 分钟视为僵死可被接管
_OWNER = f"{os.getpid()}-{random.randrange(1 << 30)}"


def _lock(name, minutes=LEASE_MIN):
    """Mongo 租约锁：已有未过期租约 → 拒绝（上一轮未完成就不开始下一轮）。"""
    now = store.now(); col = store.db().locks
    try:
        col.insert_one({"_id": name, "until": now + timedelta(minutes=minutes), "at": now, "owner": _OWNER})
        return True
    except Exception:  # noqa: BLE001 已存在
        r = col.update_one({"_id": name, "until": {"$lt": now}},
                           {"$set": {"until": now + timedelta(minutes=minutes), "at": now, "owner": _OWNER}})
        return r.modified_count == 1


def heartbeat(name="cycle"):
    store.db().locks.update_one({"_id": name, "owner": _OWNER}, {"$set": {"until": store.now() + timedelta(minutes=LEASE_MIN), "beat": store.now()}})


def cycle():
    """每 CRAWL_EVERY_HOURS 小时一轮；加锁防重叠，时间预算内未完成的目标下一轮续跑。"""
    if not _lock("cycle"):
        log.warning("previous cycle still running, skip"); return {"skipped": "locked"}
    try:
        return _cycle()
    finally:
        store.db().pipeline_runs.insert_one({"stage": "cycle_done", "at": store.now()})
        store.db().locks.delete_one({"_id": "cycle", "owner": _OWNER})


def _cycle():
    meter.reset(); t0 = time.time()
    try:
        from . import usearch; usearch.index_targets()
    except Exception:  # noqa: BLE001
        pass
    try:
        egress = check_proxy()
    except Exception as e:  # noqa: BLE001
        store.db().pipeline_runs.insert_one({"stage": "cycle", "at": store.now(), "error": str(e)[:500]})
        log.error("%s", e); return {"error": str(e)}
    run_all(); disc = run_discovery()
    purged = targets.purge()
    tgt = run_targeted(); purged += targets.purge()
    # 质量：junk/分类、无深链、聚合源缺货、链接探活（限流）
    q = {"junk": quality.apply_junk_and_category(),
         "no_url": quality.hide_no_url(),
         "oos": quality.hide_out_of_stock_aggregators(),
         "probe": quality.probe_links(limit=config.LINK_PROBE_PER_CYCLE)}
    res = {"egress": egress, "discovery": disc, "purged": purged, "targeted": tgt, "quality": q,
           "traffic": meter.snapshot(), "seconds": round(time.time() - t0)}
    store.db().pipeline_runs.insert_one({"stage": "cycle", "at": store.now(), "result": res})
    log.info("cycle done %s", {k: res[k] for k in ("egress", "targeted", "seconds")} | {"bytes": res["traffic"]["bytes"]})
    return res

daily = cycle

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    store.ensure_indexes(); targets.ensure_indexes()
    stage = sys.argv[1] if len(sys.argv) > 1 else "daily"
    print({"daily": cycle, "cycle": cycle, "discovery": run_discovery, "targeted": run_targeted, "dedupe": dedupe, "purge": targets.purge}[stage]())
