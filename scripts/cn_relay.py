#!/usr/bin/env python3
"""在**国内机器**上跑的中转代理：oracle(海外) -> 本机 -> 巨量IP 轮换 CN IP -> 目标站。

为什么必须这样：ldxp 的 ESA 判定「IP 归属地」，只放行中国 IP；而单一中国 IP 大约 40 次请求
就被 403 封（实测上海机直连 40 次后 oak/king/86ca7ta7 全挂），所以必须轮换。
偏偏巨量IP 的白名单**拒绝海外 IP**（``暂不支持向您添加的IP：140.245.91.120所属地区提供服务``），
海外服务器没法直接用它——只能由国内机器去调它。

本脚本依赖极少、不装任何软件，默认只监听 127.0.0.1（不开放公网端口，避免动安全组），
海外机通过 SSH 隧道连过来::

    # 国内机器（本机）：
    CN_RELAY_TOKEN=... CN_RELAY_UPSTREAM_URL='http://v2.api.juliangip.com/...' \
        python3 scripts/cn_relay.py --port 18080

    # 海外机器：把国内的 127.0.0.1:18080 映射到本地
    ssh -N -L 18080:127.0.0.1:18080 <cn-host>

    # 然后 app 侧：
    LDXP_PROXY_LIST=http://cn:<token>@127.0.0.1:18080

用 ``--upstream-url`` 时按 ``--upstream-ttl`` 定时重取上游 IP（巨量IP 短效默认 1 小时）；
不传则直接出口（仅用于排障）。
"""
import argparse
import asyncio
import base64
import itertools
import os
import time

import httpx

UPSTREAM = {"cycle": None, "at": 0.0, "lock": asyncio.Lock(), "url": None, "ttl": 3000, "direct": False}


async def refresh_upstream():
    """从提取接口取一批上游代理（形如 ip:port），按空白切分并兼容 ip:port,剩余秒数。"""
    if not UPSTREAM["url"]:
        return
    try:
        r = await asyncio.to_thread(lambda: httpx.get(UPSTREAM["url"], timeout=10))
        items = [t.split(",")[0].strip() for t in r.text.split() if t.strip()]
        items = [i if "://" in i else f"http://{i}" for i in items]
    except Exception as e:                                          # noqa: BLE001
        print(f"[relay] 取上游失败：{e!r}", flush=True)
        items = []
    async with UPSTREAM["lock"]:
        UPSTREAM["cycle"] = itertools.cycle(items) if items else None
        UPSTREAM["at"] = time.time()
    print(f"[relay] 上游刷新：{len(items)} 个", flush=True)


async def pick_upstream():
    if UPSTREAM["direct"]:
        return None
    if UPSTREAM["cycle"] is None or time.time() - UPSTREAM["at"] > UPSTREAM["ttl"]:
        await refresh_upstream()
    async with UPSTREAM["lock"]:
        return next(UPSTREAM["cycle"]) if UPSTREAM["cycle"] else None


def parse_upstream(p):
    p = p.split("://", 1)[-1]
    auth, _, hostport = p.rpartition("@")
    host, _, port = hostport.partition(":")
    return (host, int(port or 80)), (auth or None)


async def pipe(r, w):
    try:
        while True:
            data = await r.read(65536)
            if not data: break
            w.write(data)
            await w.drain()
    except Exception:                                               # noqa: BLE001
        pass
    finally:
        try: w.close()
        except Exception: pass


async def handle(reader, writer, token):
    first = await reader.readline()
    if not first:
        writer.close(); return
    parts = first.decode("latin-1").split()
    if len(parts) < 3:
        writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n"); await writer.drain(); writer.close(); return
    method, target, _ver = parts
    raw = first
    authorized = False
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""): break
        raw += line
        if line.lower().startswith(b"proxy-authorization:"):
            try:
                val = line.split(b" ", 1)[1].strip()
                if val[:6].lower() == b"basic ":       # 必须剥掉 scheme，否则把 "Basic" 也当 base64 解
                    val = val[6:].strip()
                got = base64.b64decode(val).decode()
                authorized = got.split(":", 1)[1] == token   # 用户名随意，口令必须是 token
            except Exception:                                # noqa: BLE001
                authorized = False
            continue                                        # 不把本地鉴权头转给上游
    if not authorized:
        writer.write(b'HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="cn-relay"\r\n'
                     b"Content-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain(); writer.close(); return

    up = await pick_upstream()
    if up is None:                                              # 直连（排障用）
        if method.upper() == "CONNECT":
            host, _, port = target.partition(":")
            u_reader, u_writer = await asyncio.open_connection(host, int(port or 443))
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n"); await writer.drain()
        else:
            # 代理请求的 target 是绝对 URL；转发给源站前必须改回 origin-form，否则多数源站直接断连
            from urllib.parse import urlsplit
            u = urlsplit(target)
            path = (u.path or "/") + (f"?{u.query}" if u.query else "")
            head, _, rest = raw.partition(b"\r\n\r\n")
            lines = head.split(b"\r\n")
            lines[0] = f"{method} {path} HTTP/1.1".encode()
            u_reader, u_writer = await asyncio.open_connection(u.hostname, u.port or 80)
            u_writer.write(b"\r\n".join(lines) + b"\r\n\r\n" + rest); await u_writer.drain()
    else:
        (uhost, uport), uauth = parse_upstream(up)
        u_reader, u_writer = await asyncio.open_connection(uhost, uport)
        if method.upper() == "CONNECT":
            head = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
            if uauth: head += f"Proxy-Authorization: Basic {base64.b64encode(uauth.encode()).decode()}\r\n"
            u_writer.write((head + "\r\n").encode()); await u_writer.drain()
            resp = await u_reader.readuntil(b"\r\n\r\n")
            if b" 200" not in resp.split(b"\r\n")[0]:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
                print(f"[relay] 上游拒绝 {target}: {resp.splitlines()[0]!r}", flush=True)
                writer.close(); u_writer.close(); return
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n"); await writer.drain()
        else:                                                    # 明文 HTTP：改写成 absolute-form 交给上游
            head, _, rest = raw.partition(b"\r\n\r\n")
            lines = head.split(b"\r\n")
            lines[0] = f"{method} {target} HTTP/1.1".encode()
            u_writer.write(b"\r\n".join(lines) + b"\r\n\r\n" + rest); await u_writer.drain()
    await asyncio.gather(pipe(reader, u_writer), pipe(u_reader, writer))


async def main_async(a):
    token = a.token or os.getenv("CN_RELAY_TOKEN", "")
    if not token:
        raise SystemExit("必须提供 --token 或 CN_RELAY_TOKEN")
    UPSTREAM["url"] = a.upstream_url or os.getenv("CN_RELAY_UPSTREAM_URL") or None
    UPSTREAM["ttl"] = a.upstream_ttl
    UPSTREAM["direct"] = not UPSTREAM["url"]
    if UPSTREAM["url"]:
        await refresh_upstream()
    server = await asyncio.start_server(lambda r, w: handle(r, w, token), a.bind, a.port)
    print(f"[relay] 监听 {a.bind}:{a.port}"
          f"{'（直连模式）' if UPSTREAM['direct'] else '（经巨量IP 轮换）'}", flush=True)
    async with server:
        await server.serve_forever()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bind", default="127.0.0.1", help="默认只监听本机，配合 SSH 隧道使用")
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--token", default="", help="本地侧 Basic 口令；也可以用 CN_RELAY_TOKEN")
    p.add_argument("--upstream-url", default="", help="巨量IP 提取链接（必须在国内机器上调用）")
    p.add_argument("--upstream-ttl", type=int, default=3000, help="上游重取间隔秒，要小于 IP 有效期")
    a = p.parse_args()
    try:
        asyncio.run(main_async(a))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
