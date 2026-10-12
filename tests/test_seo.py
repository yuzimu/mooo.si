from fastapi.testclient import TestClient

from app import store, targets
from app.main import app


def _seed(client):
    store.save_run("priceai", [{"source": "priceai", "title": "Gemini Pro 一年", "product": "Gemini Pro", "category": "gemini",
                                "price": 10, "currency": "CNY", "url": "https://shop.example.com/item/1", "seller": "s", "in_stock": True}])
    targets.upsert([("https://api.relay.example/", "relay", "中转 api", store.now())], "t")


def test_seo_and_go():
    client = TestClient(app)
    _seed(client)
    r = client.get("/")
    assert 'rel="canonical"' in r.text and "SearchAction" in r.text and 'hreflang="zh-CN"' in r.text and "ykj@mail.grokbot.com" in r.text
    assert "/go?url=https%3A%2F%2Fshop.example.com" in r.text
    assert "og:title" in client.get("/c/gemini").text
    assert client.get("/c/nope").status_code == 404
    assert "sitemap.xml" in client.get("/robots.txt").text
    assert "/c/gemini" in client.get("/sitemap.xml").text
    g = client.get("/go", params={"url": "https://shop.example.com/item/1"})
    assert g.status_code == 200 and "网络资源谨防欺诈，注意资金安全" in g.text and "shop.example.com" in g.text
    assert client.get("/go", params={"url": "https://shop.example.com/x", "ok": 1}, follow_redirects=False).status_code == 302
    for bad in ["https://evil.com/", "javascript:alert(1)", "//evil.com", "https://evil.com@shop.example.com/"]:
        assert client.get("/go", params={"url": bad, "ok": 1}, follow_redirects=False).status_code == 400
    assert client.get("/go", params={"url": "https://api.relay.example/v1", "ok": 1}, follow_redirects=False).status_code == 302
    slug = store.db().targets.find_one({"_id": "web:api.relay.example"})["slug"]
    assert client.get(f"/relay/{slug}").status_code == 200
    assert "投递店铺" in client.get("/about").text


def test_load_more_returns_fragment_on_all_routes():
    client = TestClient(app)
    for path in ["/", "/search?q=gemini", "/c/gemini"]:
        r = client.get(path + ("&" if "?" in path else "?") + "page=2&partial=1")
        assert r.status_code == 200 and "X-Has-More" in r.headers and "<html" not in r.text, path
