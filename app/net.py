"""网络层：代理池 + 指纹浏览器（CDP）钩子。"""
import itertools, random, threading
import httpx
from . import config

class ProxyPool:
    def __init__(self, static=None, url=None):
        self.static, self.url, self._lock = list(static or []), url, threading.Lock()
        self._cycle = None
    def refresh(self):
        proxies = list(self.static)
        if self.url:
            try:
                r = httpx.get(self.url, timeout=10)
                proxies += [ln.strip() for ln in r.text.splitlines() if ln.strip()]
            except httpx.HTTPError:
                pass
        random.shuffle(proxies)
        with self._lock:
            self._cycle = itertools.cycle(proxies) if proxies else None
    def get(self):
        if self._cycle is None: self.refresh()
        with self._lock:
            return next(self._cycle) if self._cycle else None

pool = ProxyPool(config.PROXY_LIST, config.PROXY_POOL_URL)

def client(use_proxy=False, **kw) -> httpx.Client:
    proxy = pool.get() if use_proxy else None
    return httpx.Client(proxy=proxy, timeout=30, follow_redirects=True,
                        headers={"User-Agent": config.USER_AGENT}, **kw)

def browser_page():
    """连接用户指纹浏览器（BROWSER_CDP_URL），返回 (playwright, browser, page)。需 pip install playwright。"""
    if not config.BROWSER_CDP_URL:
        raise RuntimeError("BROWSER_CDP_URL 未配置")
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    b = pw.chromium.connect_over_cdp(config.BROWSER_CDP_URL)
    ctx = b.contexts[0] if b.contexts else b.new_context()
    return pw, b, ctx.new_page()
