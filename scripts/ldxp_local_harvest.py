#!/usr/bin/env python3
"""本地（国内出口）跑 ldxp 采集，产出 JSONL，之后一次性导入生产。

为什么要本地跑：ldxp 的 ESA 只放行中国 IP，而生产服务器在海外；且单一中国 IP 约 40 次
请求就被 403。所以用巨量IP 的轮换国内 IP 在本地跑完，再把结果一次性提交。

复用生产同一套 adapter（app/platforms/ldxp.py），保证字段与导入格式一致::

    LDXP_PROXY_POOL_URL='<巨量IP提取链接>' \
        python scripts/ldxp_local_harvest.py --targets /tmp/ldxp_targets.tsv --out /tmp/h.jsonl --limit 30

输入每行 ``target_id<TAB>url``；输出每行一个 JSON：
``{"_id","url","ok","note","offers":[...],"meta":{...}}``（增量落盘，崩了不丢）。
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


def load_targets(path, limit):
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) < 2:
            continue
        out.append((parts[0], parts[1]))
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.8)
    a = ap.parse_args()

    targets = load_targets(a.targets, a.limit)
    proxy = ldxp.cn_proxy()
    print(f"目标 {len(targets)} 个 | 出口 {proxy or '未配置 LDXP_PROXY_*'} | 池 TTL {config.LDXP_PROXY_TTL_S}s", flush=True)
    if not proxy:
        print("未配置 LDXP_PROXY_*，本地直连会被封，请先设置"); return 2

    ok = bad = 0
    banned = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for i, (tid, url) in enumerate(targets, 1):
            token = tid.split(":", 1)[1]
            rec = {"_id": tid, "url": url, "ok": False, "note": "", "offers": [], "meta": {}}
            try:
                with net.client(proxy=ldxp.cn_proxy(), cache=False,
                                headers={"User-Agent": config.USER_AGENT}) as c:
                    good, note = ldxp.probe(c, token)
                    rec["note"] = note
                    if good:
                        offers, meta = ldxp.LdxpShop().crawl(
                            c, {"_id": tid, "url": url}, lambda: time.sleep(a.delay))
                        rec.update(ok=True, offers=[o.to_dict() for o in offers], meta=meta)
            except LdxpWafBlocked as e:
                banned += 1
                print(f"[{i}/{len(targets)}] {tid} 出口被拦：{e}", flush=True)
                f.write(json.dumps({**rec, "note": f"WAF: {e}"}, ensure_ascii=False) + "\n")
                if banned >= 5:                       # 连续被拦说明这一批 IP 废了，停下来看
                    print("连续被拦，提前结束", flush=True); break
                continue
            except Exception as e:                     # noqa: BLE001
                rec["note"] = f"{type(e).__name__}: {e}"
            banned = 0
            ok += int(rec["ok"]); bad += int(not rec["ok"])
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print(f"[{i}/{len(targets)}] {tid} {'✅' if rec['ok'] else '❌'} "
                  f"offers={len(rec['offers'])} {rec['note'][:40]}", flush=True)
            time.sleep(a.delay)
    print(f"\n完成：成功 {ok} / 失败 {bad} → {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
