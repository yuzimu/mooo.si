from .priceai import PriceAI
REGISTRY = {a.id: a for a in [PriceAI()]}
