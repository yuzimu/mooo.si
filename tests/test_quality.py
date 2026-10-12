import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.quality import guess_category, guess_subtypes, is_junk, classify_page, apply_junk_and_category, hide_no_url
from app import store


def test_categorizer_accuracy():
    labels = json.loads((Path(__file__).parent / "fixtures/categories.json").read_text())
    ok = sum(1 for L in labels if guess_category(L["title"]) == L["want"])
    assert ok / len(labels) >= 0.85, f"accuracy {ok}/{len(labels)}"
    for L in labels:
        if L.get("junk"): assert is_junk({"title": L["title"], "price": 1})
        if L.get("sub"):
            got = guess_subtypes(L["title"])
            assert any(s in got for s in L["sub"]), (L["title"], got)


def test_off_shelf_patterns():
    assert classify_page(200, "<html>商品未上架，如有疑问请联系商家</html>", "错图小铺") == "off_shelf"
    assert classify_page(200, "商品已下架或不存在") == "off_shelf"
    assert classify_page(404, "not found") == "http_404"
    assert classify_page(200, "<html><body><h1>GPT Plus 成品号 ¥129</h1><p>库存 12</p></body></html>", "GPT Plus") == "ok"


def test_hide_junk_and_nourl():
    store.db().offers.delete_many({"source": "qa"})
    store.db().offers.insert_many([
        {"source": "qa", "title": "Claude Team须知必看", "product": "x", "category": "claude", "price": 10, "url": "https://a.com/1"},
        {"source": "qa", "title": "GPT Plus 成品号", "product": "x", "category": "other", "price": 100, "url": "https://a.com/2"},
        {"source": "qa", "title": "Reddit账号", "product": "x", "category": "other", "price": 5, "url": None},
    ])
    apply_junk_and_category()
    hide_no_url()
    assert store.db().offers.find_one({"title": "Claude Team须知必看"})["junk"] is True
    assert store.db().offers.find_one({"title": "GPT Plus 成品号"})["category"] == "chatgpt"
    assert store.db().offers.find_one({"title": "Reddit账号"})["no_url"] is True
    # visible search excludes them
    items, _ = store.search(limit=50)
    titles = {o.title for o in items}
    assert "Claude Team须知必看" not in titles and "Reddit账号" not in titles
    store.db().offers.delete_many({"source": "qa"})


def test_models_page():
    store.db().relay_prices.replace_one({"_id": "web:img.test"}, {
        "_id": "web:img.test", "site": "img.test", "url": "https://img.test",
        "models": [{"model": "gpt-image-1", "price": 0.04, "unit": "次", "group_ratio": 1,
                    "model_price": 0.04, "quota_type": 1, "is_image": True},
                   {"model": "gpt-4o", "price": 2.0, "unit": "1M tokens", "group_ratio": 1, "is_image": False}]
    }, upsert=True)
    store.db().targets.update_one({"_id": "web:img.test"}, {"$set": {"type": "relay", "slug": "img-test", "url": "https://img.test",
                                                           "status": "monitored"}}, upsert=True)
    c = TestClient(app)
    r = c.get("/models")
    assert r.status_code == 200 and "gpt-image-1" in r.text and "img.test" in r.text
    assert "gpt-4o" not in r.text  # image-only default
    assert c.get("/models/gpt-image-1").status_code == 200
    store.db().relay_prices.delete_one({"_id": "web:img.test"})
