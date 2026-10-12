from types import SimpleNamespace
from app.platforms.cardsys import AcgFaka, Dujiaoka, DujiaoNext

class FakeC:
    def __init__(self, routes): self.routes = routes
    def get(self, url, params=None, timeout=None):
        key = url + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
        body = next(v for k, v in self.routes.items() if key.endswith(k))
        return SimpleNamespace(json=lambda: body if not isinstance(body, str) else None, text=body if isinstance(body, str) else "")

T = {"_id": "web:x.test", "url": "https://x.test/", "name": "X"}

def test_acg_faka():
    c = FakeC({"/user/api/index/data": {"data": [{"id": 1, "name": "GPT"}]},
               "/user/api/index/commodity?categoryId=1": {"data": [{"id": 17, "name": "GPT Plus 成品号", "price": 5, "user_price": 4,
                                                                    "stock": 0, "status": 1, "hide": 0, "inventory_hidden": 0}]}})
    offers, meta = AcgFaka().crawl(c, T, lambda: None)
    assert offers[0].price == 4 and offers[0].in_stock is False and offers[0].url == "https://x.test/item/17"

def test_dujiaoka_html():
    html = ('<div class="card position-relative"><h5 class="card-title">Gemini Pro 一年</h5>'
            '<button><strong>9.99</strong></button><h6><small>库存：15</small></h6><a href="https://x.test/buy/2">下单</a></div>')
    offers, _ = Dujiaoka().crawl(FakeC({"/": html}), T, lambda: None)
    assert offers and offers[0].price == 9.99 and offers[0].stock == 15 and offers[0].url.endswith("/buy/2")

def test_dujiao_next():
    c = FakeC({"/api/v1/public/categories": {"data": [{"id": 1, "name": {"zh-CN": "ChatGPT"}}]},
               "/api/v1/public/products?page=1&page_size=50": {"data": [{"id": 16, "category_id": 1, "slug": "plus",
                   "title": {"zh-CN": "GPT Plus 代充"}, "price_amount": "168.00"}], "pagination": {"total_page": 1}}})
    offers, _ = DujiaoNext().crawl(c, T, lambda: None)
    assert offers[0].price == 168 and offers[0].url == "https://x.test/products/plus"
