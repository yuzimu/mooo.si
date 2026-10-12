"""链动小铺店铺直采：公开 ShopApi（无需登录），与 CATFK 同一套接口范式。

参考 dimthink/PriceAI scripts/collect-prices.mjs 的实现：
- 6 个公开 POST 接口：Shop/{info,categoryList,goodsList,goodsInfo,getUserChannel,getGoodsPrice}
- base 三域名：pay.ldxp.cn（默认）/ www.ldxp.cn / ldxp.cn，故障自动切换
- 每次请求带随机 visitorid 头 + 店铺 referer（模拟 ldxp 前端访客追踪）
- 风控页结构化识别：非 JSON 响应命中 captcha/验证/风控等关键字则抛 LdxpWafBlocked
"""
import re
import secrets

from .. import config
from ..schema import Offer, guess_category

BASES = ["https://pay.ldxp.cn", "https://www.ldxp.cn", "https://ldxp.cn"]
TYPES = ["card", "article", "resource", "equity"]
PAGE_SIZE = 100
MAX_API_PAGES = 10  # PriceAI 上限 10 页

WAF_RE = re.compile(r"<html|<script|captcha|verify|challenge|验证|风控|安全", re.I)
CLOSED_RE = re.compile(r"店铺已打烊|店铺打烊|已打烊|暂停营业|停止营业|暂不营业")
REMOVED_RE = re.compile(r"未上架|已下架|商品不存在|不存在该商品|已删除|停售|无此商品")


class LdxpWafBlocked(Exception):
    """命中风控页：与普通失败区分，pipeline 侧标记而非无脑重试。"""


def _headers(token):
    return {
        "content-type": "application/json",
        "accept": "application/json, text/plain, */*",
        "visitorid": secrets.token_hex(12),
        "referer": f"https://pay.ldxp.cn/shop/{token}",
    }


def _post(c, base, path, token, payload):
    """POST ShopApi，返回 (base, data)。非 JSON 或风控页抛 LdxpWafBlocked。"""
    r = c.post(f"{base}/shopApi/Shop/{path}", json=payload,
               headers=_headers(token), timeout=20)
    try:
        d = r.json()
    except Exception as e:
        if WAF_RE.search(r.text[:2000]):
            raise LdxpWafBlocked(f"WAF page on {base}{path}") from e
        raise ValueError(f"non-JSON from {base}{path}: {r.status_code}") from e
    if isinstance(d, dict) and WAF_RE.search(str(d.get("msg", ""))):
        raise LdxpWafBlocked(f"WAF msg on {base}{path}: {d.get('msg')}")
    return d


def _post_failover(c, path, token, payload):
    """三域名故障转移：主域名失败且像出口/风控问题时切备用域名。返回 (base, data)。"""
    last = None
    for base in BASES:
        try:
            return base, _post(c, base, path, token, payload)
        except (LdxpWafBlocked, ValueError) as e:
            last = e
            continue
    raise last


def probe(c, token):
    """fingerprint 用轻探针：info 接口通即认为店铺可直采。返回 (ok, note)。"""
    try:
        base, d = _post_failover(c, "info", token, {"token": token, "category_key": ""})
    except LdxpWafBlocked as e:
        return False, f"ldxp ShopApi 风控：{e}"
    except Exception as e:
        return False, f"ldxp ShopApi 不可达：{type(e).__name__}"
    if d.get("code") == 1:
        info = (d.get("data") or {})
        if CLOSED_RE.search(str(info.get("msg", ""))):
            return False, "店铺已打烊"
        return True, info.get("nickname") or ""
    msg = str(d.get("msg", ""))
    if CLOSED_RE.search(msg):
        return False, "店铺已打烊"
    return False, msg[:80]


def parse_goods(g, token, shop_name=None):
    ext = g.get("extend") or {}
    stock = ext.get("stock_count")
    status = g.get("status", 1)
    name = g.get("name") or g.get("goods_name") or ""
    cat = (g.get("category") or {}).get("name") or ""
    goods_key = g.get("goods_key") or ""
    in_stock = (stock is None or stock > 0) and status == 1
    offers_multi = g.get("multipleoffers") or []
    return Offer(
        source="ldxp", product=name[:120], category=guess_category(f"{cat} {name}"),
        title=name, price=float(g.get("price") or 0), currency="CNY",
        seller=((g.get("user") or {}).get("nickname")) or shop_name,
        url=f"https://pay.ldxp.cn/item/{goods_key}" if goods_key else g.get("link"),
        in_stock=in_stock, stock=stock,
        tags=[t for t in (cat, g.get("goods_type")) if t],
        extra={"goods_key": goods_key, "shop": token,
               "multipleoffers": offers_multi,
               "limit_count": ext.get("limit_count"),
               "status": status})


class LdxpShop:
    def crawl(self, c, t, sleep):
        token = t["_id"].split(":", 1)[1]
        out, pages, base_used = [], 0, BASES[0]
        for gt in TYPES:
            for page in range(1, MAX_API_PAGES + 1):
                if pages >= config.MAX_PAGES_PER_TARGET:
                    break
                pages += 1
                try:
                    base, d = _post_failover(c, "goodsList", token,
                                            {"token": token, "keywords": "", "category_id": 0,
                                             "goods_type": gt, "current": page, "pageSize": PAGE_SIZE})
                except LdxpWafBlocked:
                    raise
                except Exception:
                    break
                base_used = base
                if d.get("code") != 1:
                    msg = str(d.get("msg", ""))
                    if REMOVED_RE.search(msg) or CLOSED_RE.search(msg):
                        break
                    break
                items = (d.get("data") or {}).get("list") or []
                if not items:
                    break
                # 下架/打烊消息直接读 msg，比"价格消失"可靠
                for g in items:
                    out.append(parse_goods(g, token))
                if len(items) < PAGE_SIZE:
                    break
                sleep()
            sleep()
        return out, {"goods": len(out), "pages": pages, "base": base_used}
