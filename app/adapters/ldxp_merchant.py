"""LDXP 商家后台「货源广场」搜索（/merchantApi/MyParent/searchGoodsList）。

需要用户自己的商家登录令牌 LDXP_MERCHANT_TOKEN（非公开数据），默认关闭；未配置令牌时不会发起任何请求。
不处理验证码：遇到 ESA 滑块/验证直接报错跳过。请求体字段按商家后台前端约定，接入时需用真实令牌核对。"""
from .. import config
from ..net import client
from ..schema import Offer, guess_category

URL = "https://www.ldxp.cn/merchantApi/MyParent/searchGoodsList"

def parse(data):
    d = data.get("data") or {}
    for it in d.get("list") or d.get("data") or []:
        price = it.get("price") or it.get("cost_price")
        if price is None: continue
        name = it.get("goods_name") or it.get("name") or ""
        stock = it.get("stock") or it.get("stock_count")
        yield Offer(source="ldxp-merchant", product=name[:120], category=guess_category(name), title=name,
                    price=float(price), currency="CNY", seller=it.get("shop_name") or it.get("nickname"),
                    url=it.get("link") or it.get("url"), in_stock=(stock or 0) > 0, stock=stock,
                    tags=["货源广场"], extra={"goods_id": it.get("goods_id") or it.get("id")})

class LdxpMerchant:
    id, use_proxy, use_browser = "ldxp-merchant", False, False
    enabled = False  # 显式开启：设置 LDXP_MERCHANT_TOKEN 且 ENABLED_ADAPTERS 包含 ldxp-merchant
    raw = None
    def fetch(self):
        if not config.LDXP_MERCHANT_TOKEN: raise RuntimeError("LDXP_MERCHANT_TOKEN 未配置")
        out = []
        with client(self.use_proxy, headers={"Authorization": config.LDXP_MERCHANT_TOKEN,
                                             "token": config.LDXP_MERCHANT_TOKEN}) as c:
            for kw in config.LDXP_MERCHANT_KEYWORDS:
                r = c.post(URL, json={"keyword": kw, "page": 1, "limit": 50})
                if "captcha" in r.text.lower() or r.status_code in (403, 429):
                    raise RuntimeError(f"LDXP 返回 {r.status_code}/验证，已跳过")
                r.raise_for_status(); out += list(parse(r.json()))
        return out
