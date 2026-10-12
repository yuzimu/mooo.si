"""AIGOOD 价格雷达 aigood.chat/price-radar。
robots 禁止 /api/，因此只解析公开 HTML 列表页（SSR），按页限速，默认抓前 AIGOOD_PAGES 页。"""
import re
from bs4 import BeautifulSoup
from .. import config
from ..net import client
from ..schema import Offer, guess_category
from ._util import parse_price, polite_sleep

BASE = "https://aigood.chat/price-radar"
STOCK_RE = re.compile(r"有货\s*(\d+)?")

def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for art in soup.find_all("article"):
        h2 = art.find("h2")
        if not h2: continue
        title = h2.get_text(strip=True)
        spans = [s.get_text(" ", strip=True) for s in art.find_all("span")]
        text = art.get_text(" ", strip=True)
        price, cur = parse_price(text.replace("CNY ", "CNY"))
        if not price: continue
        link = next((a["href"] for a in art.find_all("a", href=True) if a["href"].startswith("http")), None)
        t = art.find("time")
        sm = STOCK_RE.search(text)
        platform = next((s for s in spans if s in ("LDXP", "CatFK", "WZYP", "Z2U", "G2G")), None)
        kinds = [e.get_text(strip=True) for e in art.find_all("span", class_=lambda c: c and "border-divider" in c)]
        kind = next((k for k in kinds if k and "暂无商品图片" not in k), "")
        shops_el = art.find_all("p")
        seller = None
        if len(shops_el) > 1: seller = shops_el[-1].get_text(" ", strip=True)[:120]
        yield Offer(source="aigood", product=title[:120], category=guess_category(f"{kind} {title}"),
                    title=title, price=price, currency=cur or "CNY", seller=seller, url=link,
                    in_stock=bool(sm), stock=int(sm.group(1)) if sm and sm.group(1) else None,
                    captured_at=t.get("datetime") if t else None, tags=[x for x in (kind, platform) if x],
                    extra={"platform": platform})

class AIGood:
    id, use_proxy, use_browser = "aigood", False, False
    raw = None
    def fetch(self):
        out, pages = [], []
        with client(self.use_proxy, headers={"User-Agent": config.BROWSER_UA}) as c:
            for p in range(1, config.AIGOOD_PAGES + 1):
                r = c.get(BASE, params={"page": p} if p > 1 else None); r.raise_for_status()
                got = list(parse(r.text)); out += got; pages.append({"page": p, "count": len(got)})
                if not got: break
                polite_sleep()
        self.raw = {"pages": pages}
        return out
