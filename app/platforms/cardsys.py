"""常见开源发卡系统的公开前台接口（均为店铺前端自身调用、无需登录/验证码）：

- 异次元 acg-faka：GET /user/api/index/data（分类）+ /user/api/index/commodity?categoryId=（商品，含 price/stock）
- 独角数卡 dujiaoka（unicorn/luna/hyper 主题）：首页服务端渲染商品卡片，/buy/<id>
- dujiao-next（Vue3 新版独角）：GET /api/v1/public/categories、/api/v1/public/products?page=&page_size=

接口路径为实地观察（公开前台），实现为本项目自写。
"""
import re
from html import unescape
from urllib.parse import urljoin
from .. import config
from ..schema import Offer, guess_category


def _zh(v):
    if isinstance(v, dict): return v.get("zh-CN") or v.get("zh-TW") or v.get("en-US") or next((x for x in v.values() if x), "")
    return v or ""


class AcgFaka:
    def crawl(self, c, t, sleep):
        base = t["url"].rstrip("/"); site = t.get("name") or t["_id"].split(":", 1)[1]
        cats = (c.get(base + "/user/api/index/data", timeout=15).json() or {}).get("data") or []
        out = []
        for cat in cats[: config.MAX_PAGES_PER_TARGET * 2]:
            sleep()
            r = c.get(f"{base}/user/api/index/commodity", params={"categoryId": cat.get("id")}, timeout=15)
            for g in (r.json() or {}).get("data") or []:
                if g.get("hide") or g.get("status") == 0: continue
                name = g.get("name") or ""; cn = (g.get("category") or {}).get("name") or cat.get("name") or ""
                stock = g.get("stock") if not g.get("inventory_hidden") else None
                price = g.get("user_price") if g.get("user_price") not in (None, "") else g.get("price")
                out.append(Offer(source="acg-faka", product=name[:120], category=guess_category(f"{cn} {name}"), title=name,
                                 price=float(price or 0), currency="CNY", seller=site, url=f"{base}/item/{g.get('id')}",
                                 in_stock=stock is None or stock > 0, stock=stock, tags=[x for x in (cn, "acg-faka") if x],
                                 extra={"id": g.get("id"), "sold": g.get("order_sold")}))
        return out, {"goods": len(out), "categories": len(cats)}


CARD_RE = re.compile(r'<div class="card[^"]*"(.*?)href="([^"]*/buy/(\d+))"', re.S)

class Dujiaoka:
    def crawl(self, c, t, sleep):
        base = t["url"].rstrip("/"); site = t.get("name") or t["_id"].split(":", 1)[1]
        h = c.get(base + "/", timeout=15).text
        out = []; seen = set()
        for m in CARD_RE.finditer(h):
            blk, href, gid = m.group(1), m.group(2), m.group(3)
            if gid in seen: continue
            seen.add(gid)
            blk = blk[-3000:]
            names = re.findall(r"<h[56][^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,120})", blk)
            name = unescape(next((n.strip() for n in names if n.strip() and "库存" not in n), "")).strip()
            pm = re.findall(r"(?:<strong>|[¥￥]\s*)([\d]+(?:\.\d+)?)", blk)
            sm = re.search(r"库存[：:]\s*(\d+)", blk)
            if not name or not pm: continue
            stock = int(sm.group(1)) if sm else None
            out.append(Offer(source="dujiaoka", product=name[:120], category=guess_category(name), title=name,
                             price=float(pm[-1]), currency="CNY", seller=site, url=urljoin(base + "/", href),
                             in_stock=stock is None or stock > 0, stock=stock, tags=["dujiaoka"], extra={"id": gid}))
        return out, {"goods": len(out)}


class DujiaoNext:
    def crawl(self, c, t, sleep):
        base = t["url"].rstrip("/"); site = t.get("name") or t["_id"].split(":", 1)[1]
        cats = {x.get("id"): _zh(x.get("name")) for x in ((c.get(base + "/api/v1/public/categories", timeout=15).json() or {}).get("data") or [])}
        out = []
        for page in range(1, config.MAX_PAGES_PER_TARGET + 1):
            sleep()
            j = c.get(base + "/api/v1/public/products", params={"page": page, "page_size": 50}, timeout=15).json() or {}
            for g in j.get("data") or []:
                name = _zh(g.get("title")); cn = cats.get(g.get("category_id"), "")
                stock = next((g.get(k) for k in ("stock", "stock_count", "available_stock", "inventory") if isinstance(g.get(k), int)), None)
                out.append(Offer(source="dujiao-next", product=name[:120], category=guess_category(f"{cn} {name}"), title=name,
                                 price=float(g.get("price_amount") or g.get("price") or 0), currency="CNY", seller=site,
                                 url=f"{base}/products/{g.get('slug') or g.get('id')}",
                                 in_stock=stock is None or stock > 0, stock=stock, tags=[x for x in (cn, "dujiao-next") if x],
                                 extra={"id": g.get("id"), "fulfillment": g.get("fulfillment_type")}))
            pg = j.get("pagination") or {}
            if page >= (pg.get("total_page") or 1): break
        return out, {"goods": len(out), "categories": len(cats)}
