#!/usr/bin/env python3
"""一次性批量指纹：清掉 ldxp 目标的「待识别」积压。

背景（2026-10-12）：旧逻辑曾把全部 ldxp 目标批量标成 blocked_captcha（滑块跳过）；
修复后其中 18458 个被重置为 new（待识别），但 pipeline 每轮只处理
TARGET_CRAWL_MAX=300 个目标、每 2 小时一轮——靠正常调度要 ~5 天才能清完。

本脚本直接对这些目标跑 fingerprint()（ldxp 走 ShopApi info 轻探针，单个 POST），
写入的字段与 pipeline._crawl_domain 的指纹分支逐字一致：
    upd = {"fp": fp, "fp_at": now, "status": fp["status"], "priority": priority(t)}
    + platform / name 回填 + health + history（只保留最近 10 条）
只做指纹、不抓取：状态 ok 的目标下一轮正常调度会接手抓取（指纹 7 天内有效，
本脚本写入的 health.at=now 会让它在 TARGET_MIN_INTERVAL_H=6h 后参与抓取）。

幂等：只处理「pipeline 本轮会重新指纹」的目标（fp 缺失/为空/fp_at 超过 7 天），
中途可 Ctrl-C，可重复执行收尾。

运行（Oracle 的 mooo-si 容器内，MONGO_URL 由容器 .env 提供，无需重建镜像）：
    docker cp scripts/batch_fp_ldxp.py mooo-si:/tmp/batch_fp_ldxp.py
    docker exec -e PYTHONPATH=/app mooo-si python /tmp/batch_fp_ldxp.py --dry-run
    docker exec -e PYTHONPATH=/app mooo-si python /tmp/batch_fp_ldxp.py --limit 50
    docker exec -e PYTHONPATH=/app mooo-si python /tmp/batch_fp_ldxp.py --workers 20

耗时估算：18458 个 × 单次 POST（通常 <1s，超时 20s/域名×3 兜底），20 并发约 10~25 分钟。
"""
import argparse
import math
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

# 让脚本无论从仓库根还是被 docker cp 到 /tmp 都能 import app（容器内再配 PYTHONPATH=/app）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(_REPO_ROOT, "app")) and _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app import config, store                      # noqa: E402
from app.net import client as make_client          # noqa: E402
from app.platforms import fingerprint              # noqa: E402

FP_TTL = timedelta(days=7)  # 与 pipeline._crawl_domain 的指纹有效期一致


def priority(t):
    """与 app/pipeline.py::priority 保持一致（复制，避免引入 pipeline 的重依赖）。"""
    age_days = 30
    if t.get("last_seen"):
        ls = t["last_seen"]
        if ls.tzinfo is None:
            ls = ls.replace(tzinfo=store.now().tzinfo)
        age_days = (store.now() - ls).days
    return round(math.log2(1 + t.get("mentions", 1)) * 10
                 + max(0, 30 - age_days) + len(t.get("sources") or {}) * 3, 2)


def needs_fp(t, now):
    """与 pipeline 逐字一致的「本轮是否需要重新指纹」判定。"""
    fp = t.get("fp") if t.get("fp_at") and now - t["fp_at"].replace(tzinfo=now.tzinfo) < FP_TTL else None
    return not fp


_tls = threading.local()


def get_client():
    c = getattr(_tls, "client", None)
    if c is None:
        c = _tls.client = make_client(headers={"User-Agent": config.BROWSER_UA}, cache=False)
    return c


def process_one(tid, t, jitter):
    """单个目标：指纹 -> 写回（成功/异常两条路径都与 pipeline 一致）。返回 status。"""
    col = store.db().targets
    now = store.now()
    health = {"at": now}
    try:
        time.sleep(random.uniform(0, jitter))
        fp = fingerprint(get_client(), t)  # ldxp: ShopApi info 轻探针
        upd = {"fp": fp, "fp_at": now, "status": fp["status"], "priority": priority(t)}
        if fp.get("platform"):
            upd["platform"] = fp["platform"]
        if fp.get("name") and not t.get("name"):
            upd["name"] = fp["name"][:80]
        if fp.get("platform") in ("new-api", "one-api") and t.get("type") == "unknown":
            upd["type"] = "relay"
        # 只指纹不抓取：与 pipeline「fp ok 但无对应 crawler」分支的 health 写法一致
        health.update(ok=fp["status"] == "ok",
                      skipped=fp["status"] if fp["status"] != "ok" else "no_adapter",
                      note=fp.get("note"))
        status = fp["status"]
    except Exception as e:  # noqa: BLE001
        health.update(ok=False, error=repr(e)[:300])
        # 与 pipeline 的 except 分支一致：异常不写 fp，下轮还会重试指纹
        upd = {"status": "private" if re.search(r"HTTP 40[13]|需登录", repr(e)) else "error"}
        status = upd["status"]
    col.update_one({"_id": tid},
                   {"$set": {**upd, "health": health},
                    "$push": {"history": {"$each": [health], "$slice": -10}}})
    return status


def main():
    ap = argparse.ArgumentParser(description="批量指纹 ldxp 待识别目标")
    ap.add_argument("--workers", type=int, default=20, help="并发数（默认 20）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（0=全部；先小批量验证用）")
    ap.add_argument("--dry-run", action="store_true", help="只统计候选数，不发请求不写库")
    ap.add_argument("--jitter", type=float, default=0.3, help="每请求随机延迟上限秒（默认 0.3）")
    a = ap.parse_args()

    store.db()  # 主线程先初始化 mongo client，避免多线程竞态
    col = store.db().targets
    now = store.now()

    proj = {"platform": 1, "type": 1, "url": 1, "fp": 1, "fp_at": 1, "status": 1,
            "name": 1, "mentions": 1, "last_seen": 1, "sources": 1, "tg_public": 1}
    cands = [t for t in col.find({"platform": "ldxp"}, proj) if needs_fp(t, now)]
    # 待识别（new）优先，其次按下架/风控等已有状态分组处理
    cands.sort(key=lambda t: (t.get("status") != "new", t["_id"]))
    if a.limit:
        cands = cands[:a.limit]
    print(f"[batch-fp] ldxp 候选 {len(cands)} 个（fp 缺失/过期），"
          f"其中 status=new {sum(1 for t in cands if t.get('status') == 'new')} 个", flush=True)
    if a.dry_run:
        for t in cands[:10]:
            print("  dry:", t["_id"], t.get("status"), (t.get("fp") or {}).get("status"))
        return

    counts, done, t0 = {}, 0, time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(process_one, t["_id"], t, a.jitter): t["_id"] for t in cands}
        for f in as_completed(futs):
            try:
                st = f.result()
            except Exception as e:  # noqa: BLE001
                st = f"thread_error:{type(e).__name__}"
            counts[st] = counts.get(st, 0) + 1
            done += 1
            if done % 500 == 0 or done == len(cands):
                el = time.time() - t0
                print(f"[batch-fp] {done}/{len(cands)}  {el:.0f}s  {counts}", flush=True)
    print(f"[batch-fp] 完成：{done} 个，{time.time() - t0:.0f}s，结果分布 {counts}", flush=True)


if __name__ == "__main__":
    main()
