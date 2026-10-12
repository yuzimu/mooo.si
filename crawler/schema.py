"""统一数据模型 Offer。"""
from dataclasses import dataclass, asdict, field
from typing import Optional

CATEGORIES = ["gcp-trial", "gemini", "adobe-firefly", "leonardo", "nano-banana-api",
              "api-relay", "chatgpt", "claude", "ai-tool", "other"]

@dataclass
class Offer:
    source: str            # 数据源 id，如 priceai
    product: str           # 标准商品名
    category: str
    title: str
    price: float
    currency: str = "CNY"
    seller: Optional[str] = None
    url: Optional[str] = None
    in_stock: Optional[bool] = None
    stock: Optional[int] = None
    captured_at: Optional[str] = None
    tags: list = field(default_factory=list)
    def to_dict(self): return asdict(self)

def guess_category(text: str) -> str:
    t = text.lower()
    rules = [("gcp", "gcp-trial"), ("google cloud", "gcp-trial"), ("gemini", "gemini"),
             ("firefly", "adobe-firefly"), ("adobe", "adobe-firefly"), ("leonardo", "leonardo"),
             ("nano banana", "nano-banana-api"), ("中转", "api-relay"), ("api", "api-relay"),
             ("chatgpt", "chatgpt"), ("openai", "chatgpt"), ("claude", "claude")]
    for k, c in rules:
        if k in t: return c
    return "other"
