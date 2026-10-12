from crawler.adapters.priceai import parse
def test_parse():
    snap = {"products": [{"name": "Gemini Pro", "platform": "Gemini", "top_offers": [
        {"title": "x", "price": 9.9, "status": "in_stock", "source_name": "s", "url": "u"}]}]}
    o = list(parse(snap)); assert len(o) == 1 and o[0].category == "gemini" and o[0].in_stock
