#!/usr/bin/env python3
"""把 ldxp_local_harvest.py 产出的 JSONL 一次性导入生产库。

在容器里跑（要能连 Mongo）::

    sudo docker cp h678.jsonl mooo-si:/tmp/h.jsonl
    sudo docker exec mooo-si python scripts/ldxp_import_harvest.py /tmp/h.jsonl

只写 ``ok=true`` 的记录：offers 交给 store.save_target_offers（dedupe/分类与线上一致），
目标本身置为 monitored 并清掉 ldxp_canary_blocked。失败记录一律不动——避免又把目标
批量毒化成 blocked_captcha。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store          # noqa: E402


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/h.jsonl"
    rows = [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    col = store.db().targets
    ok = offers = 0
    skipped = []
    for r in rows:
        tid = r.get("_id")
        if not tid or not r.get("ok"):
            skipped.append((tid, r.get("note", "")[:50]))
            continue
        store.save_target_offers(tid, r.get("offers") or [])
        name = (r.get("note") or "").strip() or None
        col.update_one({"_id": tid}, {
            "$set": {"status": "monitored", "name": name,
                     "fp": {"platform": "ldxp", "status": "ok", "name": name},
                     "fp_at": store.now(),
                     "health": {"at": store.now(), "ok": True, "offers": len(r.get("offers") or []), **(r.get("meta") or {})}},
            "$unset": {"ldxp_canary_blocked": ""}}, upsert=True)
        ok += 1
        offers += len(r.get("offers") or [])
    print(f"导入完成：目标 {ok} 个，报价 {offers} 条；跳过 {len(skipped)} 条未成功记录")
    for tid, note in skipped[:10]:
        print(f"  跳过 {tid}: {note}")
    print("ldxp 目标状态分布:", {s: col.count_documents({"platform": "ldxp", "status": s})
                              for s in ("monitored", "blocked_captcha", "new", "down", "error")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
