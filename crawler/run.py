import json, datetime, pathlib
from .adapters.priceai import PriceAI
ADAPTERS = [PriceAI()]
def main(out="site/data/offers.json"):
    offers, errors = [], {}
    for a in ADAPTERS:
        try: offers += [o.to_dict() for o in a.fetch()]
        except Exception as e: errors[a.id] = str(e)
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "count": len(offers), "errors": errors, "offers": offers},
              open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{len(offers)} offers, errors={errors}")
if __name__ == "__main__": main()
