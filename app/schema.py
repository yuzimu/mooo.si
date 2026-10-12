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
    extra: dict = field(default_factory=dict)   # 各来源特有字段，原样存入 Mongo
    def to_dict(self): return asdict(self)

# 分类元数据：id -> (中文名, lucide 图标, 所属栏目)
CATEGORIES = {
    "gcp-trial": ("GCP 试用号", "cloud", "cards"),
    "gemini": ("Gemini / Google AI", "sparkles", "cards"),
    "chatgpt": ("ChatGPT / Codex", "message-square", "cards"),
    "claude": ("Claude", "feather", "cards"),
    "grok": ("Grok", "zap", "cards"),
    "adobe-firefly": ("Adobe Firefly", "flame", "tools"),
    "leonardo": ("Leonardo", "palette", "tools"),
    "nano-banana-api": ("Nano Banana 生图", "image", "relay"),
    "api-relay": ("API 中转", "network", "relay"),
    "ai-tool": ("AI 工具账号", "wand-sparkles", "tools"),
    "email": ("邮箱账号", "mail", "cards"),
    "verify": ("接码 / KYC", "shield-check", "cards"),
    "payment": ("虚拟卡 / 礼品卡", "credit-card", "cards"),
    "social": ("社交 / 会员", "users", "cards"),
    "other": ("其他", "package", "cards"),
}
SECTIONS = {"cards": "卡网", "relay": "中转", "tools": "AI 工具"}

RULES = [("gcp", "gcp-trial"), ("google cloud", "gcp-trial"), ("nano banana", "nano-banana-api"),
         ("firefly", "adobe-firefly"), ("adobe", "adobe-firefly"), ("leonardo", "leonardo"),
         ("中转", "api-relay"), (" api", "api-relay"),
         ("接码", "verify"), ("kyc", "verify"), ("验证", "verify"),
         ("邮箱", "email"), ("gmail", "email"), ("outlook", "email"),
         ("虚拟卡", "payment"), ("礼品卡", "payment"), ("paypal", "payment"),
         ("gemini", "gemini"), ("google ai", "gemini"), ("grok", "grok"),
         ("chatgpt", "chatgpt"), ("gpt", "chatgpt"), ("codex", "chatgpt"), ("openai", "chatgpt"), ("claude", "claude"),
         ("cursor", "ai-tool"), ("kiro", "ai-tool"), ("perplexity", "ai-tool"), ("suno", "ai-tool"),
         ("dreamina", "ai-tool"), ("即梦", "ai-tool"), ("muse", "ai-tool"), ("midjourney", "ai-tool"),
         ("telegram", "social"), ("推特", "social"), ("twitter", "social"), ("x premium", "social"),
         ("apple", "social"), ("多邻国", "social")]

def guess_category(text: str) -> str:
    t = " " + (text or "").lower()
    return next((c for k, c in RULES if k in t), "other")
