#!/usr/bin/env python3
"""验证一个国内出口能不能过 ldxp 的阿里云 ESA，并检查整条链路。

用法（在容器/服务器上跑，或本地）::

    python scripts/verify_ldxp_egress.py                    # 用配置里的 LDXP_PROXY_*，没配回落主代理池
    python scripts/verify_ldxp_egress.py 'http://u:p@1.2.3.4:8080'
    python scripts/verify_ldxp_egress.py '1.2.3.4:8080'

判据（走的是抓取用的同一条代码路径）：ESA 放行时 ShopApi 返回 JSON；被拦时返回
HTML 挑战页，代码里会抛 LdxpWafBlocked。

**买代理前先用免费试用跑这个脚本** —— 「国内 IP 能过」目前只在中国住宅和中国机房各一个 IP
上验证过，共享代理池里的 IP 有可能已被 ESA 标记。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import net                                             # noqa: E402
from app.platforms import ldxp                                  # noqa: E402
from app.platforms.ldxp import BASES, LdxpRedirect, LdxpWafBlocked, _post   # noqa: E402

TOKENS = ["oak", "king", "86ca7ta7"]


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg:
        proxy = net.norm_proxy(arg)
        print(f"显式出口: {proxy}")
    else:
        proxy = ldxp.cn_proxy()
        print(f"LDXP_PROXY_* 出口: {proxy or '（未配置）'}")
        if not proxy:
            proxy = net.pool.get()
            print(f"回落到主代理池出口: {proxy}")

    if not proxy:
        print("没有可用出口（PROXY_REQUIRED=1 下不允许直连）")
        return 2

    try:
        with net.client(proxy=proxy, cache=False) as c:
            print(f"出口公网 IP: {c.get('https://api.ipify.org', timeout=20).text.strip()}")
    except Exception as e:                                      # noqa: BLE001
        # 探不到出口 IP 不代表出口不能用（有些环境屏蔽 ipify）；继续做真正要紧的 ldxp 探测。
        print(f"（取出口 IP 失败，忽略：{type(e).__name__}）")

    ok_any = False
    for tok in TOKENS:
        try:
            with net.client(proxy=proxy, cache=False) as c:
                d = _post(c, BASES[0], "info", tok, {"token": tok, "category_key": ""})
            info = d.get("data") or {}
            print(f"  {tok:10s} ✅ 放行   code={d.get('code')} nickname={info.get('nickname')!r} goods={len(info.get('goods') or [])}")
            ok_any = True
        except LdxpWafBlocked as e:
            print(f"  {tok:10s} ❌ ESA 拦截 {e}")
        except LdxpRedirect as e:
            print(f"  {tok:10s} ⚠️  跳转 {e}")
        except Exception as e:                                  # noqa: BLE001
            print(f"  {tok:10s} ⚠️  {type(e).__name__}: {e}")

    print()
    if ok_any:
        print("结论：该出口能过 ESA ✅ 把代理串填进 LDXP_PROXY_LIST（或提取接口填 LDXP_PROXY_POOL_URL）即可。")
        return 0
    print("结论：该出口过不了 ESA ❌ 换 IP / 换服务商，别买年付。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
