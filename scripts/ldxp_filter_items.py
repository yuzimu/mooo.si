#!/usr/bin/env python3
"""把不是店铺的 ldxp item 目标过滤掉（标 ignored）。

线上 18458 个 ldxp 目标 = 679 个真店铺 + 17779 个 /item/ 商品页。商品页不是店铺，
展示在 /shops 里只会是空壳；它们的价值是当店铺发现源（见 ldxp_resolve_items.py），
反查出来的店铺会被单独作为 ldxp:<token> 目标补进来。

所以这里把 item 目标统一标成 ignored（从 /shops 与采集队列里摘掉），保留原始 url 与
解析出来的 shop 供追溯。

用法::

    sudo docker exec mooo-si python scripts/ldxp_filter_items.py            # 只看统计
    sudo docker exec mooo-si python scripts/ldxp_filter_items.py --apply    # 真的标记
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store          # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    col = store.db().targets
    q = {"platform": "ldxp", "_id": {"$regex": "^ldxp:item:"}}
    total = col.count_documents(q)
    # 反查结果里有店铺的 item 单独记一笔，便于以后追溯
    mapped = col.count_documents({**q, "item_shop": {"$exists": True}})
    print(f"item 目标 {total} 个（其中已记录所属店铺的 {mapped} 个）")
    print("当前状态分布:", {s: col.count_documents({**q, "status": s})
                        for s in ("blocked_captcha", "ignored", "monitored", "new")})
    if not apply:
        print("\n这是预演。加 --apply 才会真的标记 ignored。")
        return 0
    r = col.update_many(q, {"$set": {"status": "ignored", "ignored_reason": "item 商品页，非店铺"},
                            "$unset": {"fp": "", "fp_at": "", "ldxp_canary_blocked": ""}})
    print(f"\n已标记 ignored: {r.modified_count} 个")
    print("ldxp 目标:", {s: col.count_documents({"platform": "ldxp", "status": s})
                      for s in ("monitored", "ignored", "blocked_captcha", "new", "down")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
