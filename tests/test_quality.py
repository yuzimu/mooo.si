import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.quality import guess_category, is_junk, classify_page, apply_junk_and_category, hide_no_url, product_key
from app import store


def test_categorizer_accuracy():
    labels = json.loads((Path(__file__).parent / "fixtures/categories.json").read_text())
    ok = sum(1 for L in labels if guess_category(L["title"]) == L["want"])
    assert ok / len(labels) >= 0.85, f"accuracy {ok}/{len(labels)}"
    for L in labels:
        if L.get("junk"): assert is_junk({"title": L["title"], "price": 1})
        if L.get("key"): assert product_key(L["title"]).startswith(L["key"]), (L["title"], product_key(L["title"]))
        if L.get("key_prefix"): assert product_key(L["title"]).startswith(L["key_prefix"]), (L["title"], product_key(L["title"]))
    # 谷歌免费账号簇必须归一
    keys = {product_key(t) for t in ["谷歌免费账号", "Gmail新号", "谷歌邮箱", "Gmail邮箱/2FA/随机地区"]}
    assert len({k.split(":")[0] for k in keys}) == 1 and all(k.startswith("gmail") for k in keys)



def test_is_junk_ads_and_tutorials():
    """首页广告/科普/找微引流应 junk；正常定价商品保留。"""
    junk_cases = [
        ("获取Plus方式：印度区UPI完成订阅", {"tags": ["科普", "article"]}),
        ("G羊毛党与OpenAI的风控系统_科普版", {"tags": ["科普"]}),
        ("日区PP无卡筛Plus教程", {}),
        ("GPT 成品号寿命和渠道说明", {}),
        ("plus延迟到账问题", {"tags": ["常见问题", "article"]}),
        ("需要PLUS充值找微seven9485777", {}),
        ("学生优惠活动全流程讲解", {}),
        ("纯说明帖仅图文不含账号", {}),
        ("随便什么标题", {"tags": ["article"]}),
        ("购买指南请先阅读", {}),
    ]
    for title, extra in junk_cases:
        o = {"title": title, "price": 10, **extra}
        assert is_junk(o), title

    keep = [
        "bugteam invite ChatGPT Plus",
        "Gplus质保成品号",
        "Team K12 席位",
        "codex橙皮书 成品号",
        "Claude Pro 代充",
    ]
    for title in keep:
        assert not is_junk({"title": title, "price": 99}), title


def test_off_shelf_patterns():
    assert classify_page(200, "<html>商品未上架，如有疑问请联系商家</html>", "错图小铺") == "off_shelf"
    assert classify_page(200, "商品已下架或不存在") == "off_shelf"
    assert classify_page(404, "not found") == "http_404"
    assert classify_page(200, "<html><body><h1>GPT Plus 成品号 ¥129</h1><p>库存 12</p></body></html>", "GPT Plus") == "ok"


def test_hide_junk_and_nourl():
    store.db().offers.delete_many({"source": "qa"})
    store.db().offers.insert_many([
        {"source": "qa", "title": "Claude Team须知必看", "product": "x", "category": "account", "price": 10, "url": "https://a.com/1"},
        {"source": "qa", "title": "GPT Plus 成品号", "product": "x", "category": "other", "price": 100, "url": "https://a.com/2"},
        {"source": "qa", "title": "Reddit账号", "product": "x", "category": "other", "price": 5, "url": None},
    ])
    apply_junk_and_category()
    hide_no_url()
    assert store.db().offers.find_one({"title": "Claude Team须知必看"})["junk"] is True
    assert store.db().offers.find_one({"title": "GPT Plus 成品号"})["category"] == "account"
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
    assert r.status_code == 200 and ("gpt-image" in r.text or "图片" in r.text)
    assert "图片" in r.text  # bucket label
    assert c.get("/models/gpt-image-1").status_code == 200
    store.db().relay_prices.delete_one({"_id": "web:img.test"})


def test_relay_never_on_home_or_search():
    store.db().offers.delete_many({"source": {"$in": ["qa", "relay"]}})
    store.save_run("qa", [{"source": "qa", "title": "GPT Plus 成品号", "product": "x", "category": "account",
                           "price": 100, "currency": "CNY", "url": "https://shop.example.com/a", "seller": "s", "in_stock": True}])
    store.db().offers.insert_one({"source": "relay", "title": "gpt-4o · $2/1M tokens", "product": "gpt-4o",
                                  "category": "api-relay", "price": 2, "currency": "USD", "url": "https://relay.example/",
                                  "seller": "r", "in_stock": True, "dup": None})
    client = TestClient(app)
    home = client.get("/").text
    assert "gpt-4o" not in home and "1M tokens" not in home
    assert "GPT Plus" in home or "成品号" in home
    assert client.get("/c/api-relay", follow_redirects=False).status_code in (302, 307)
    assert client.get("/?section=relay", follow_redirects=False).status_code in (302, 307)
    store.db().offers.delete_many({"source": {"$in": ["qa", "relay"]}})


def test_model_families():
    from app.models_tax import family_of, group_models
    assert family_of("gpt-4o-mini-2024-07-18") == ("chatgpt", "gpt-4o-mini")
    assert family_of("gemini-2.5-flash-image-preview")[0] == "image"
    assert family_of("deepseek-v3-chat")[0] == "china"
    rows = [
        {"model": "gpt-4o-mini-a", "price": 0.1, "unit": "1M tokens", "site": "A"},
        {"model": "gpt-4o-mini-b", "price": 0.05, "unit": "1M tokens", "site": "B"},
        {"model": "gpt-image-2.5-flare", "price": 0.01, "unit": "次", "site": "C"},
    ]
    g = group_models(rows)
    labs = {x["id"] for x in g}
    assert "chatgpt" in labs and "image" in labs
    chat = next(x for x in g if x["id"] == "chatgpt")
    assert chat["families"][0]["family"] == "gpt-4o-mini" and chat["families"][0]["min"] == 0.05


def test_family_versions_and_aliases():
    from app.models_tax import classify
    c = lambda n: classify(n)[:2]  # noqa: E731
    assert c("nano-banana") == ("image", "gemini-2.5-flash-image")
    assert c("nano-banana-2-4k") == ("image", "gemini-3.1-flash-image")
    assert c("gemini-3.1-flash-image-preview") == ("image", "gemini-3.1-flash-image")
    assert c("nana-banana-pro") == ("image", "gemini-3-pro-image")
    assert c("gemini-nano-banana-2.1") == ("image", "nano-banana-2.1")   # 未知新版本独立
    assert c("nano-banana-2-1") == ("image", "nano-banana-2.1")
    assert c("doubao-seedance-2-5-260628") == ("video", "seedance-2.5")
    assert c("seedance-2-fast-特价版") == ("video", "seedance-2.0")
    assert c("aigc-video-kling-2.1") == ("video", "kling-2.1")
    assert c("veo_3_1-fast") == ("video", "veo-3.1")
    assert c("doubao-seed-2.1-pro")[0] == "china"
    assert c("MiniMax-M2.1")[0] == "china"


def test_estimate_and_rate():
    from app.models_tax import estimate, rate_info
    r = rate_info({"quota_display_type": "USD", "price": 1})
    assert r["rmb_per_quota_usd"] == 1 and r["mislabeled"]
    e = estimate({"quota_type": 0, "model_ratio": 3.3823529, "completion_ratio": 3.3823529, "group_ratio": 1}, "video", "seedance-2.0", 6.8)
    assert abs(e["per_s_usd"] - 6.7647 * 3.3823529 * 0.0216) < 0.01 or e["per_s_usd"] > 0
    e = estimate({"quota_type": 1, "model_price": 0.0014706, "group_ratio": 1.13}, "video", "kling", 1)
    assert e["suspect"]
    e = estimate({"quota_type": 1, "model_price": 0.12923, "group_ratio": 0.1369}, "image", "nano-banana-2.1", 1)
    assert abs(e["cny"] - 0.0177) < 0.001
