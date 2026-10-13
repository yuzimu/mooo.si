"""网络层：代理池（强制）、带宽统计、条件请求缓存、指纹浏览器（CDP）钩子。

- PROXY_REQUIRED=1 时所有抓取流量必须走代理池；代理不可用则 fail closed（抛 ProxyUnavailable，不直连）。
- 条件请求：GET 自动带 If-None-Match / If-Modified-Since；304 时返回缓存的正文（http_cache 集合，≤3MB）。
- 带宽：每个 Client 统计下载字节，汇总到全局计数器，管线结束写入 pipeline_runs。"""
import hashlib, itertools, random, threading, time
import httpx
from . import config

class ProxyUnavailable(RuntimeError):
    pass

def norm_proxy(p):
    """把代理串规整成 httpx 能用的 URL。

    兼容提取接口的两种返回：`1.2.3.4:8080`（无 scheme）与 `1.2.3.4:8080,281`
    （带 ip_remain 剩余秒数后缀）。也保留 `http://user:pass@host:port` 形式。
    """
    if not p: return None
    p = p.strip().split(",")[0].strip()
    return p if "://" in p else f"http://{p}"

class ProxyPool:
    def __init__(self, static=None, url=None, ttl=0):
        self.static, self.url, self._lock = list(static or []), url, threading.Lock()
        self._cycle = None
        self.ttl = ttl     # >0 时按秒定时重取（短效代理 IP 会过期）
        self._at = 0.0
    def refresh(self):
        proxies = list(self.static)
        if self.url:
            try:
                r = httpx.get(self.url, timeout=10)
                # 提取接口可能一行一个，也可能 `ip:port,剩余秒数`（ip_remain）。按空白切分，
                # 再逐条去掉逗号后缀——不能直接把逗号换成换行，否则剩余秒数会被当成一个代理。
                proxies += [tok.split(",")[0].strip() for tok in r.text.split() if tok.strip()]
            except httpx.HTTPError:
                pass
        proxies = [p for p in proxies if p]
        random.shuffle(proxies)
        with self._lock:
            self._cycle = itertools.cycle(proxies) if proxies else None
            self._at = time.time()
    def get(self):
        if self._cycle is None or (self.ttl and time.time() - self._at > self.ttl):
            self.refresh()
        with self._lock:
            return next(self._cycle) if self._cycle else None

pool = ProxyPool(config.PROXY_LIST, config.PROXY_POOL_URL)

class Meter:
    def __init__(self): self.lock = threading.Lock(); self.reset()
    def reset(self):
        self.bytes = 0; self.requests = 0; self.not_modified = 0; self.by_host = {}
    def add(self, host, n, nm=False):
        with self.lock:
            self.bytes += n; self.requests += 1; self.not_modified += int(nm)
            self.by_host[host] = self.by_host.get(host, 0) + n
    def snapshot(self):
        top = sorted(self.by_host.items(), key=lambda x: -x[1])[:15]
        return {"bytes": self.bytes, "requests": self.requests, "not_modified": self.not_modified,
                "top_hosts": [{"host": h, "bytes": b} for h, b in top]}

meter = Meter()
MAX_CACHE_BODY = 3_000_000

class CrawlClient(httpx.Client):
    def __init__(self, *a, cache=True, **kw):
        super().__init__(*a, **kw); self.cache = cache
    def send(self, request, **kw):
        cached = None
        if self.cache and request.method == "GET":
            from . import store
            key = hashlib.sha1(str(request.url).encode()).hexdigest()
            cached = store.db().http_cache.find_one({"_id": key})
            if cached:
                if cached.get("etag"): request.headers["If-None-Match"] = cached["etag"]
                if cached.get("last_modified"): request.headers["If-Modified-Since"] = cached["last_modified"]
        resp = super().send(request, **kw)
        resp.read()
        nm = resp.status_code == 304 and cached is not None
        meter.add(request.url.host, len(resp.content), nm)
        if nm:
            resp = httpx.Response(200, headers={**dict(resp.headers), "content-type": cached.get("ctype", "")},
                                  content=cached["body"], request=request)
            resp.extensions["not_modified"] = True
        elif self.cache and request.method == "GET" and resp.status_code == 200 and len(resp.content) <= MAX_CACHE_BODY \
                and (resp.headers.get("etag") or resp.headers.get("last-modified")):
            from . import store
            store.db().http_cache.replace_one({"_id": hashlib.sha1(str(request.url).encode()).hexdigest()}, {
                "_id": hashlib.sha1(str(request.url).encode()).hexdigest(), "url": str(request.url),
                "etag": resp.headers.get("etag"), "last_modified": resp.headers.get("last-modified"),
                "ctype": resp.headers.get("content-type", ""), "body": resp.content}, upsert=True)
        return resp

def client(use_proxy=True, headers=None, cache=True, proxy=None, pool_=None, **kw) -> httpx.Client:
    """proxy= 显式指定出口（如按平台走不同地域的池）；pool_= 换一个池来取出口。"""
    p = pool_ or pool
    proxy = norm_proxy(proxy) or (p.get() if (use_proxy or config.PROXY_REQUIRED) else None)
    if config.PROXY_REQUIRED and not proxy:
        raise ProxyUnavailable("PROXY_REQUIRED=1 但代理池为空，拒绝直连")
    h = {"User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip, deflate", **(headers or {})}
    return CrawlClient(proxy=proxy, timeout=30, follow_redirects=True, headers=h, cache=cache, **kw)

def check_proxy() -> str:
    """管线开始前确认代理可用；失败则 fail closed。返回出口 IP。"""
    if not config.PROXY_REQUIRED: return "proxy-not-required"
    try:
        with client(cache=False) as c:
            r = c.get("https://api.ipify.org", timeout=15); r.raise_for_status(); return r.text.strip()
    except (httpx.HTTPError, ProxyUnavailable) as e:
        raise ProxyUnavailable(f"代理不可用，停止本轮抓取：{e!r}") from e

def browser_page():
    """连接用户指纹浏览器（BROWSER_CDP_URL）。仅在确有必要的目标上使用；屏蔽图片/字体/媒体/样式以省带宽。
    注意：浏览器自身的出口代理需在指纹浏览器配置中设为同一代理池。"""
    if not config.BROWSER_CDP_URL:
        raise RuntimeError("BROWSER_CDP_URL 未配置")
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    b = pw.chromium.connect_over_cdp(config.BROWSER_CDP_URL)
    ctx = b.contexts[0] if b.contexts else b.new_context()
    page = ctx.new_page()
    page.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "media", "font", "stylesheet")
               else route.continue_())
    return pw, b, page
