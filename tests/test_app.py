from fastapi.testclient import TestClient
from app.adapters.priceai import parse
from app.schema import Offer, guess_category
from app.net import ProxyPool
from app import crawler, store
from app.main import app

SNAP = {"products": [{"name": "Gemini Pro", "platform": "Gemini", "top_offers": [
    {"title": "Gemini 家庭位", "price": 9.9, "status": "in_stock", "source_name": "s", "url": "https://x"},
    {"title": "说明贴", "price": 0, "status": "in_stock"}]}]}

def test_parse():
    o = list(parse(SNAP)); assert len(o) == 1 and o[0].category in ("account","gcp-trial","gemini") and o[0].in_stock

def test_category():
    assert guess_category("GCP $300 试用") == "gcp-trial"
    assert guess_category("Nano Banana 按张") == "image-api"
    assert guess_category("Google / Gemini 接码") == "verify"

def test_tokens_chinese():
    t = store.tokens("Claude Max 家庭位")
    assert {"claude", "cl", "max", "家庭", "庭位", "家"} <= t
    assert store.query_tokens("家庭位 cla") == ["家庭", "庭位", "cla"]

def test_proxy_pool_rotates():
    p = ProxyPool(["http://a:1", "http://b:2"]); got = {p.get() for _ in range(4)}
    assert got == {"http://a:1", "http://b:2"}
    assert ProxyPool().get() is None

class Fake:
    id, use_proxy, use_browser = "fake", False, False
    raw = {"hello": "world"}
    def fetch(self):
        return [Offer("fake", "Leonardo 积分", "leonardo", "Leonardo 年付 家庭位", 12.5, in_stock=True, seller="A"),
                Offer("fake", "Leonardo 积分", "leonardo", "Leonardo 月付", 3.0, in_stock=False, seller="B"),
                Offer("fake", "Claude Pro", "account", "Claude Pro 成品号", 99.0, in_stock=True, seller="C")]

class Boom(Fake):
    id = "boom"
    def fetch(self): raise RuntimeError("x")

def test_crawl_search_and_web():
    store.db().client.drop_database("mooo_test"); store.ensure_indexes()
    assert crawler.run_adapter(Fake()).count == 3
    assert crawler.run_adapter(Boom()).error
    assert store.db().raw.count_documents({"source": "fake"}) == 1
    c = TestClient(app)
    assert c.get("/healthz").json() == {"ok": True}
    r = c.get("/api/search", params={"q": "家庭位"}).json()
    assert r["total"] == 1 and r["items"][0]["seller"] == "A"
    r = c.get("/api/search", params={"q": "leo", "in_stock": "true"}).json(); assert r["total"] == 1
    r = c.get("/api/search", params={"category": "family", "sort": "-price"}).json()
    assert [i["price"] for i in r["items"]] == [12.5]
    r = c.get("/api/search", params={"category": "ai-tool"}).json()
    assert any(i["price"] == 3.0 for i in r["items"])
    r = c.get("/api/search", params={"max_price": 10}).json(); assert r["total"] == 1
    assert c.get("/api/offers", params={"source": "fake"}).status_code == 200
    for path in ["/", "/search?q=claude", "/?section=relay", "/?section=tools", "/about"]:
        assert c.get(path).status_code == 200, path
    assert "Leonardo" in c.get("/").text
    assert c.get("/?section=relay", follow_redirects=False).status_code == 302
    assert "生图" in c.get("/models").text or "模型" in c.get("/models").text


def test_public_only_ok_and_gone():
    """公开页面与 API 只有「正常 / 下架」两种状态。

    抓取失败、不可达、未知平台、滑块、CF 盾、待识别这些是我们的管线状态，不是店铺下架的
    证据 —— 一律折叠成「正常」且不显示这些词，也不因为一次抓取失败就把店铺从目录里摘掉。
    只有 ignored（我们主动不要的，比如非店铺的 item 页）整个不进公开视图。
    """
    from app import targets
    db = store.db(); db.client.drop_database("mooo_test"); store.ensure_indexes()
    for tid, st in [("ldxp:ok1", "monitored"), ("ldxp:ok2", "monitored"), ("ldxp:gone1", "item_gone"),
                    ("ldxp:err", "error"), ("ldxp:cap", "blocked_captcha"), ("ldxp:down", "down"),
                    ("ldxp:unk", "unknown"), ("ldxp:ign", "ignored")]:
        db.targets.insert_one({"_id": tid, "type": "card_shop", "platform": "ldxp", "status": st,
                               "url": f"https://x.example/{tid.split(':')[1]}", "slug": tid.replace(":", "-")})
    assert targets.public_status("monitored") == "ok" and targets.public_status("item_gone") == "gone"
    assert targets.public_status("error") == "ok" and targets.public_status("down") == "ok"
    assert targets.public_status("ignored") is None
    assert targets.public_status_counts(type="card_shop") == {"ok": 6, "gone": 1}

    c = TestClient(app)
    r = c.get("/api/targets", params={"type": "card_shop"}).json()
    assert r["total"] == 7 and {i["status"] for i in r["items"]} == {"ok", "gone"}   # ignored 不进公开结果
    assert all(i["status_label"] in ("正常", "下架") for i in r["items"])
    assert "ignored" not in c.get("/api/targets", params={"type": "card_shop"}).text

    html = c.get("/shops").text
    for leak in ("抓取失败", "不可达", "滑块验证", "CF 盾", "未知平台", "monitored", "blocked_captcha", "item_gone"):
        assert leak not in html, f"页面泄漏内部状态：{leak}"
    assert "正常" in html and "下架" in html
    assert "下架" in c.get("/shops", params={"status": "gone"}).text        # 公开筛选可用
    assert "抓取失败" not in c.get("/shops", params={"status": "error"}).text  # 内部状态筛选不回显

    assert c.get("/shop/ldxp-ign").status_code == 404        # 主动剔除的目标不给看
    assert c.get("/shop/ldxp-ok1").status_code == 200
    assert c.get("/shop/ldxp-gone1").status_code == 200
    assert c.get("/shop/ldxp-err").status_code == 200        # 抓取失败仍是正常店铺，页面要能开
    db.client.drop_database("mooo_test")
