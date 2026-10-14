#!/usr/bin/env python3
"""把 item（商品页 wzyp.cn/item/<goods_key>）反查成所属店铺。

`Shop/goodsInfo` 传 ``{"goods_key": <id>}`` 返回里带 ``data.user.token`` / ``user.link``，
即该商品所属店铺的 token 与地址。item 目标本身不是店铺（拿去做 Shop/info 会返回
"店铺链接不存在"），但可以当**店铺发现源**用。

用法::

    LDXP_PROXY_POOL_URL='<巨量IP提取链接>' \
        python scripts/ldxp_resolve_items.py --items /tmp/items_new.txt --out /tmp/item_shops.jsonl

输出每行 ``{"item","shop","name","status"}``，status 为 ok / gone / fail；增量落盘。
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, net                     # noqa: E402
from app.platforms import ldxp                  # noqa: E402
from app.platforms.ldxp import LdxpWafBlocked   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.4)
    a = ap.parse_args()

    ids = [ln.strip() for ln in Path(a.items).read_text().splitlines() if ln.strip()]
    if a.limit:
        ids = ids[:a.limit]
    print(f"待解析 item {len(ids)} 个 | 出口 {ldxp.cn_proxy() or '未配置'}", flush=True)

    ok = gone = fail = banned = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for i, gk in enumerate(ids, 1):
            rec = {"item": gk, "shop": None, "name": None, "status": "fail"}
            try:
                with net.client(proxy=ldxp.cn_proxy(), cache=False,
                                headers={"User-Agent": config.USER_AGENT}) as c:
                    d = ldxp._post(c, ldxp.BASES[0], "goodsInfo", "", {"goods_key": gk})
                if d.get("code") == 1:
                    u = (d.get("data") or {}).get("user") or {}
                    if u.get("token"):
                        rec.update(shop=u["token"], name=u.get("nickname"), status="ok"); ok += 1
                    else:
                        rec["status"] = "gone"; gone += 1
                else:
                    rec["status"] = "gone"; gone += 1
            except LdxpWafBlocked as e:
                banned += 1
                print(f"[{i}/{len(ids)}] 出口被拦：{e}", flush=True)
                if banned >= 5:
                    print("连续被拦，提前结束", flush=True); break
                continue
            except Exception as e:                       # noqa: BLE001
                rec["status"] = f"fail:{type(e).__name__}"; fail += 1
            banned = 0
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            if i % 25 == 0 or rec["status"] == "ok":
                print(f"[{i}/{len(ids)}] ok={ok} gone={gone} fail={fail} | {rec['shop'] or '-'}", flush=True)
            time.sleep(a.delay)
    print(f"\n完成：解析出店铺 {ok} / 已下架 {gone} / 失败 {fail} → {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
