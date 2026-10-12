"""统一报价结构 + 封闭分类（按商品形态，不按品牌拆分）。"""
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
    extra: dict = field(default_factory=dict)
    def to_dict(self): return asdict(self)

# 封闭分类：id -> (中文名, lucide 图标, 栏目)
# 形态优先于品牌：同一「谷歌免费号」不再拆到 email/chatgpt/other
CATEGORIES = {
    "account": ("成品号", "user-round", "cards"),          # ChatGPT/Claude/Gemini/Grok/Cursor 等成品账号
    "topup": ("代充 / CDK", "credit-card", "cards"),       # 官方代充、直充、CDK、续费
    "family": ("家庭组 / 车位", "users", "cards"),         # 家庭位、拼车、席位
    "api-relay": ("API 中转", "network", "relay"),         # 中转站额度 / 模型按量
    "image-api": ("生图 / 视频 API", "image", "relay"),    # gpt-image、flux、banana、veo 等
    "verify": ("接码 / KYC", "shield-check", "cards"),
    "email": ("邮箱", "mail", "cards"),                   # Gmail/Outlook/iCloud 等纯邮箱
    "gcp-trial": ("GCP 试用", "cloud", "cards"),
    "payment": ("虚拟卡 / 礼品卡", "wallet", "cards"),
    "social": ("社交 / 会员", "message-circle", "cards"), # TG/X/Apple ID/多邻国等
    "ai-tool": ("AI 工具账号", "wand-sparkles", "tools"), # Cursor/Kiro/Perplexity 等（非大厂对话账号）
    "api-credit": ("API 额度卡", "key", "cards"),
    "other": ("未知", "package", "cards"),
}
SECTIONS = {"cards": "卡网", "relay": "中转", "tools": "AI 工具"}

# 旧分类 → 新分类（迁移用；细规则在 quality.guess_category）
LEGACY_MAP = {
    "chatgpt": "account", "claude": "account", "gemini": "account", "grok": "account",
    "nano-banana-api": "image-api", "adobe-firefly": "ai-tool", "leonardo": "ai-tool",
}

def guess_category(text: str) -> str:
    from .quality import guess_category as _g
    return _g(text)

def product_key(text: str) -> str:
    from .quality import product_key as _p
    return _p(text)

def cat_meta(cid: str):
    label, icon, section = CATEGORIES.get(cid, CATEGORIES["other"])
    return {"id": cid, "label": label, "icon": icon, "section": section}
