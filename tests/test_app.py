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
