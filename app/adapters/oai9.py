"""oai9.com「LDXP 货源查询」（LDXP / CATFK 商品搜索 + 24 小时热卖榜）。

状态：2026-10-12 调研时源站经 Cloudflare 返回 502（box 与 oracle 均如此），无法确认页面/接口结构。
适配器默认关闭；源站恢复后在 OAI9_HOT_URL 配置其公开热卖榜 JSON 地址（robots 允许的公开接口）即可启用。
期望 JSON：{"items":[{"name","price","stock","sales_24h","platform","shop","url"}]}，字段名做了宽松映射。"""
from .. import config
from ..net import client
from ..schema import Offer, guess_category

def _g(d, *keys):
    return next((d[k] for k in keys if d.get(k) is not None), None)

def parse(data):
    items = data.get("items") or data.get("data") or data.get("list") or []
    for it in items:
        price = _g(it, "price", "minPrice", "min_price")
        if price is None: continue
        name = _g(it, "name", "title", "goodsName") or ""
        yield Offer(source="oai9", product=name[:120], category=guess_category(name), title=name, price=float(price),
                    currency=_g(it, "currency") or "CNY", seller=_g(it, "shop", "shopName", "merchant"),
                    url=_g(it, "url", "link", "itemUrl"), in_stock=(_g(it, "stock", "stockCount") or 1) > 0,
                    stock=_g(it, "stock", "stockCount"), tags=[x for x in (_g(it, "platform"), "24h 热卖") if x],
                    extra={"sales_24h": _g(it, "sales_24h", "sales24h", "salesDelta")})

class Oai9Hot:
    id, use_proxy, use_browser = "oai9", False, False
    enabled = bool(config.OAI9_HOT_URL)
    raw = None
    def fetch(self):
        if not config.OAI9_HOT_URL: raise RuntimeError("OAI9_HOT_URL 未配置（源站 502，接口待确认）")
        with client(self.use_proxy) as c:
            r = c.get(config.OAI9_HOT_URL); r.raise_for_status(); self.raw = r.json()
        return list(parse(self.raw))
