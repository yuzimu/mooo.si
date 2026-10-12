from dataclasses import dataclass, asdict, field

@dataclass
class Offer:
    source: str
    product: str
    category: str
    title: str
    price: float
    currency: str = "CNY"
    seller: str | None = None
    url: str | None = None
    in_stock: bool | None = None
    stock: int | None = None
    captured_at: str | None = None
    tags: list = field(default_factory=list)
    def to_dict(self): return asdict(self)

RULES = [("gcp", "gcp-trial"), ("google cloud", "gcp-trial"), ("gemini", "gemini"),
         ("firefly", "adobe-firefly"), ("adobe", "adobe-firefly"), ("leonardo", "leonardo"),
         ("nano banana", "nano-banana-api"), ("中转", "api-relay"), ("api", "api-relay"),
         ("chatgpt", "chatgpt"), ("openai", "chatgpt"), ("claude", "claude")]

def guess_category(text: str) -> str:
    t = (text or "").lower()
    return next((c for k, c in RULES if k in t), "other")
