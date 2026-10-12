"""中转模型：归桶（国模/ChatGPT/Claude/Gemini/Grok/图片/视频）、家族+版本推导、别名合并、计费归一。

家族从实时模型名推导（line + version），只对**已知等价**做别名合并；未知新版本（如 nano-banana-2.1）保留为独立家族。
"""
import re
from collections import defaultdict

# ---------------- 名称规范化 ----------------
PREFIX_JUNK = re.compile(r"^(?:熊猫[^a-z]*|按量-?|满血[^a-z]*|特供[^a-z]*|s{1,3}-|aigc-|[\u4e00-\u9fff]+-)+", re.I)

def _norm(name: str) -> str:
    n = (name or "").strip().lower()
    n = n.replace("_", "-").replace(" ", "-")
    n = PREFIX_JUNK.sub("", n)
    n = n.replace("nana-banana", "nano-banana")
    n = re.sub(r"[-（(]?(特价版|补贴版|vip|官转|逆向)[)）]?", "", n)
    return n.strip("-")

def _ver(s: str | None) -> str | None:
    """'2-5' / '2.5' / '25'(仅 seedance 风格两位) → '2.5'；'2' → '2'"""
    if not s: return None
    s = s.strip("-.")
    m = re.fullmatch(r"(\d)[-.](\d)", s)
    if m: return f"{m.group(1)}.{m.group(2)}"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", s)
    return m.group(1) if m else s

# ---------------- 家族规则（有序） ----------------
# 每条: (regex, bucket, builder(match)->(family, variant))
VARIANT_RE = re.compile(r"(fast|mini|lite|pro|turbo|flash|hd|2k|4k|1080p|720p|i2v|t2v|relaxed|quality|preview)", re.I)

def _variant(rest: str) -> str:
    v = [m.group(1).lower() for m in VARIANT_RE.finditer(rest or "")]
    return "-".join(dict.fromkeys(v))

# 已知等价（Google 官方命名）：nano-banana ↔ gemini-*-image
NANO_ALIAS = {
    None: "gemini-2.5-flash-image",      # nano-banana (1)
    "2": "gemini-3.1-flash-image",       # nano-banana-2
    "pro": "gemini-3-pro-image",         # nano-banana-pro
}
GEMINI_IMAGE_ALIAS = {v: k for k, v in NANO_ALIAS.items()}

def _nano(m):
    tail = m.group(1) or ""
    ver = None
    mm = re.match(r"-?(pro)\b", tail)
    if mm: ver = "pro"
    else:
        mm = re.match(r"-?(\d+(?:[.-]\d(?![\dkp]))?)(?![\dkp])", tail)
        if mm: ver = _ver(mm.group(1))
    rest = tail[mm.end():] if mm else tail
    if ver in NANO_ALIAS:
        fam = NANO_ALIAS[ver]
    else:
        fam = f"nano-banana-{ver}"       # 未知新版本保持独立，例如 nano-banana-2.1
    return fam, _variant(rest)

def _gem_img(m):
    ver, kind, rest = m.group(1), m.group(2), m.group(3) or ""
    fam = f"gemini-{ver}-{kind}-image"
    return fam, _variant(rest)

def _simple(line):
    def f(m):
        ver = _ver(m.group(1)) if m.lastindex and m.group(1) else None
        rest = m.group(m.lastindex) if m.lastindex and m.lastindex > 1 else ""
        if ver and line == "seedance" and "." not in ver: ver += ".0"
        return (f"{line}-{ver}" if ver else line), _variant(rest or "")
    return f

FAMILY_RULES = [
    # ---- 图片 ----
    (re.compile(r"(?:gemini-)?nano-banana(.*)$"), "image", _nano),
    (re.compile(r"gemini-(\d+(?:\.\d+)?)-(flash-lite|flash|pro)-image(.*)$"), "image", _gem_img),
    (re.compile(r"gpt-image-?(\d+(?:\.\d+)?)?(.*)$"), "image", _simple("gpt-image")),
    (re.compile(r"dall-?e-?(\d)?(.*)$"), "image", _simple("dall-e")),
    (re.compile(r"grok-imagine-image(?:-(\d+(?:\.\d+)?))?(.*)$"), "image", _simple("grok-imagine-image")),
    (re.compile(r"(?:doubao-)?seedream-?(\d(?:[-.]\d)?)?(.*)$"), "image", _simple("seedream")),
    (re.compile(r"imagen-?(\d(?:[-.]\d)?)?(.*)$"), "image", _simple("imagen")),
    (re.compile(r"flux[-.]?(\d(?:[-.]\d)?)?(.*)$"), "image", _simple("flux")),
    (re.compile(r"(?:stable-diffusion|sdxl|sd)-?(\d(?:\.\d)?)?(.*)$"), "image", _simple("stable-diffusion")),
    (re.compile(r"(?:midjourney|mj)[-_]?(?:v)?(\d(?:\.\d)?)?(.*)$"), "image", _simple("midjourney")),
    (re.compile(r"qwen-image(?:-(\w+))?(.*)$"), "image", lambda m: ("qwen-image", _variant((m.group(1) or "") + (m.group(2) or "")))),
    (re.compile(r"(reve|recraft|ideogram|kolors|cogview|wanx|agnes-image|jimeng-image|pixverse-image)"
                r"-?(\d(?:\.\d)?)?(.*)$"), "image",
     lambda m: ((f"{m.group(1)}-{_ver(m.group(2))}" if m.group(2) else m.group(1)), _variant(m.group(3) or ""))),
    # ---- 视频 ----
    (re.compile(r"(?:doubao-)?seedance-?(\d(?:[-.]\d)?)?(.*)$"), "video", _simple("seedance")),
    (re.compile(r"veo-?(\d(?:[-.]\d)?)?(.*)$"), "video", _simple("veo")),
    (re.compile(r"(?:aigc-video-)?kling(?:-video)?-?(\d(?:\.\d)?)?(.*)$"), "video", _simple("kling")),
    (re.compile(r"sora-?(\d)?(.*)$"), "video", _simple("sora")),
    (re.compile(r"(?:minimax-)?hailuo-?(\d+)?(.*)$"), "video", _simple("hailuo")),
    (re.compile(r"wan-?(\d(?:[.-]\d)?)-image(.*)$"), "image", _simple("wan-image")),
    (re.compile(r"wan-?(\d(?:\.\d)?)(.*)$"), "video", _simple("wan")),
    (re.compile(r"grok-imagine-video(?:-(\d+(?:\.\d+)?))?(.*)$"), "video", _simple("grok-imagine-video")),
    (re.compile(r"(vidu|runway|luma|pixverse|jimeng-video)-?(\d(?:\.\d)?)?(.*)$"), "video",
     lambda m: ((f"{m.group(1)}-{_ver(m.group(2))}" if m.group(2) else m.group(1)), _variant(m.group(3) or ""))),
]

TEXT_BUCKETS = [
    ("claude", re.compile(r"claude|anthropic")),
    ("gemini", re.compile(r"gemini|gemma")),
    ("grok", re.compile(r"\bgrok")),
    ("chatgpt", re.compile(r"^(?:openai/)?(gpt|o\d|chatgpt|codex|davinci|whisper|tts|text-embedding)")),
    ("china", re.compile(r"deepseek|qwen|qwq|glm|chatglm|doubao|seed-|kimi|moonshot|hunyuan|yi-|01-ai|minimax|abab|"
                         r"baichuan|ernie|sparkdesk|spark|sensenova|step-|internlm|skylark|longcat|ling-|mimo")),
]

TEXT_CANON = [
    (re.compile(r"^(?:anthropic/)?claude-(opus|sonnet|haiku)-?(\d(?:[-.]\d)?)?"), lambda m: f"claude-{m.group(1)}" + (f"-{_ver(m.group(2))}" if m.group(2) else "")),  # noqa: E501
    (re.compile(r"^claude-(\d(?:[-.]\d)?)-(opus|sonnet|haiku)"), lambda m: f"claude-{m.group(2)}-{_ver(m.group(1))}"),
    (re.compile(r"^claude-(\d(?:\.\d)?)$"), lambda m: f"claude-{m.group(1)}"),
    (re.compile(r"^gemini-(\d+(?:\.\d+)?)-(pro|flash-lite|flash)"), lambda m: f"gemini-{m.group(1)}-{m.group(2)}"),
    (re.compile(r"^(?:openai/)?gpt-(\d+(?:\.\d+)?)(o)?-?(mini|nano|pro|codex-max|codex|chat)?"),
     lambda m: "gpt-" + m.group(1) + (m.group(2) or "") + (f"-{m.group(3)}" if m.group(3) else "")),
    (re.compile(r"^(o\d)(?:-(mini|pro))?"), lambda m: m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")),
    (re.compile(r"^grok-(\d+(?:\.\d+)?)(?:-(mini|fast|code|heavy))?"), lambda m: f"grok-{m.group(1)}" + (f"-{m.group(2)}" if m.group(2) else "")),
    (re.compile(r"^(?:deepseek/)?deepseek-(r\d|v\d+(?:[.-]\d)?|chat|reasoner|coder)"), lambda m: "deepseek-" + (("v" + _ver(m.group(1)[1:])) if m.group(1)[0] == "v" else m.group(1))),  # noqa: E501
    (re.compile(r"^(qwen\d*(?:\.\d+)?)(?:-(max|plus|turbo|coder|vl|long))?"), lambda m: m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")),
    (re.compile(r"^(glm-\d(?:\.\d)?)"), lambda m: m.group(1)),
    (re.compile(r"^(?:doubao-)?(seed-\d(?:\.\d)?)"), lambda m: "doubao-" + m.group(1)),
    (re.compile(r"^(kimi-k\d(?:\.\d)?|moonshot-v\d)"), lambda m: m.group(1)),
    (re.compile(r"^(?:minimax/)?minimax-(m\d(?:\.\d)?)"), lambda m: f"minimax-{m.group(1)}"),
]

BUCKET_ORDER = ["chatgpt", "claude", "gemini", "grok", "china", "image", "video", "other"]
BUCKET_LABEL = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "grok": "Grok",
                "china": "国模", "image": "图片", "video": "视频", "other": "未知"}


def family_of(name: str) -> tuple[str, str]:
    b, fam, _v = classify(name)
    return b, fam


def classify(name: str) -> tuple[str, str, str]:
    """→ (bucket, family, variant)"""
    n = _norm(name)
    for rx, bucket, build in FAMILY_RULES:
        m = rx.search(n)
        if m:
            # 防误伤：seed-2.1（豆包文本）≠ seedance；sd 只在开头
            if bucket == "image" and rx.pattern.startswith("(?:stable") and not re.match(r"(stable-diffusion|sdxl|sd-?\d)", n):
                continue
            fam, var = build(m)
            return bucket, fam, var
    bucket = next((b for b, rx in TEXT_BUCKETS if rx.search(n)), "other")
    fam = n
    for rx, f in TEXT_CANON:
        m = rx.search(n)
        if m: fam = f(m); break
    else:
        fam = re.sub(r"[-_](preview|latest|exp|thinking|c|\d{6,8})$", "", n)
    return bucket, fam, ""


# ---------------- 计费归一 ----------------
# 假设（页面 tooltip 展示）
ASSUME = {
    "image_tokens": {"gpt-image": 1056, "default": 1290},   # 1024² medium：gpt-image≈1056 输出 token；Gemini 图≈1290
    "video_clip_s": {"veo": 8, "sora": 10, "default": 5},
    "video_tokens_per_s": 21600,                            # 720p×24fps：1280*720*24/1024
    "fallback_rmb_per_usd": 7.2,
}

def _clip_s(fam: str) -> int:
    for k, v in ASSUME["video_clip_s"].items():
        if k != "default" and fam.startswith(k): return v
    return ASSUME["video_clip_s"]["default"]

def _img_tokens(fam: str) -> int:
    return ASSUME["image_tokens"]["gpt-image"] if fam.startswith("gpt-image") else ASSUME["image_tokens"]["default"]

def estimate(row: dict, bucket: str, fam: str, rmb_per_usd: float | None) -> dict:
    """row 需含 quota_type/model_price/model_ratio/completion_ratio/group_ratio。返回 $ 与 ¥ 估算 + 说明。"""
    qt = row.get("quota_type"); mp = row.get("model_price") or 0; mr = row.get("model_ratio") or 0
    cr = row.get("completion_ratio"); gr = row.get("group_ratio") or 1
    cr = cr if cr not in (None, 0) else 1
    if not mp and not mr and row.get("price"):  # 旧数据只存了换算后价格
        if row.get("unit") == "次": mp, qt = row["price"] / gr, 1
        else: mr = row["price"] / 2 / gr
    rate = rmb_per_usd or ASSUME["fallback_rmb_per_usd"]
    out = {"billing": None, "usd": None, "unit": None, "per_s_usd": None, "clip5_usd": None, "clip10_usd": None,
           "note": "", "suspect": False}
    if qt == 1 or (mp and not mr):
        call = mp * gr
        out["billing"] = "按次"
        if bucket == "image":
            out.update(usd=call, unit="张", note="按次计费：model_price × 分组倍率 = 每次调用（≈1 张图）")
            if call < 0.002: out.update(suspect=True, note=out["note"] + "；单价异常低，站点可能按积分/秒另计")
        elif bucket == "video":
            secs = _clip_s(fam)
            out.update(usd=call, unit=f"条(≈{secs}s)", per_s_usd=call / secs, clip5_usd=call / secs * 5, clip10_usd=call / secs * 10,
                       note=f"按次计费：假设每次生成 {secs}s 视频")
            if call < 0.05: out.update(suspect=True, note="按次单价异常低（<$0.05/条），站点实际多按秒/积分计费，仅供参考")
        else:
            out.update(usd=call, unit="次")
    else:
        inp = mr * 2 * gr; outp = mr * cr * 2 * gr
        out["billing"] = "按量"
        if bucket == "image":
            t = _img_tokens(fam)
            out.update(usd=outp * t / 1e6, unit="张", note=f"按量：输出 ${outp:.4g}/1M × 约 {t} token/张（1024²）")
        elif bucket == "video":
            tps = ASSUME["video_tokens_per_s"]
            ps = outp * tps / 1e6
            out.update(usd=ps * 5, unit="条(5s)", per_s_usd=ps, clip5_usd=ps * 5, clip10_usd=ps * 10,
                       note=f"按量：${outp:.4g}/1M × 约 {tps} token/秒（720p 24fps）")
        else:
            out.update(usd=inp, unit="1M 输入", note=f"输出 ${outp:.4g}/1M")
    for k in ("usd", "per_s_usd", "clip5_usd", "clip10_usd"):
        if out[k] is not None:
            out[k] = round(out[k], 6)
            out[k.replace("usd", "cny")] = round(out[k] * rate, 4)
    out["rate"] = rate
    if rmb_per_usd is not None and rmb_per_usd < 0.3:
        out["suspect"] = True; out["note"] += f"；充值单价 ¥{rmb_per_usd}/$ 异常低，需核对"
    return out


def group_models(rows: list[dict]) -> list[dict]:
    """rows: {model, price(¥ 估算优先), unit, site, ...}"""
    fams = defaultdict(list)
    for r in rows:
        b, fam, var = classify(r.get("model") or "")
        r = {**r, "bucket": r.get("bucket") or b, "family": fam, "variant": var}
        fams[(r["bucket"], fam)].append(r)
    buckets = defaultdict(list)
    for (b, fam), offers in fams.items():
        offers = [o for o in offers if (o.get("cny") or o.get("price") or 0) > 0]
        if not offers: continue
        key = lambda x: (x.get("suspect", False), x.get("cny") if x.get("cny") is not None else x.get("price") or 0)  # noqa: E731
        offers.sort(key=key)
        variants = defaultdict(list)
        for o in offers: variants[o["model"]].append(o)
        var_list = []
        for vn, vo in variants.items():
            vo.sort(key=key)
            var_list.append({"name": vn, "cheapest": vo[0], "count": len(vo), "offers": vo[:15],
                             "min": vo[0].get("cny") if vo[0].get("cny") is not None else vo[0].get("price"), "usd": vo[0].get("price"), "unit": vo[0].get("unit")})  # noqa: E501
        var_list.sort(key=lambda v: key(v["cheapest"]))
        alias = GEMINI_IMAGE_ALIAS.get(fam)
        alias_name = ("nano-banana" if alias is None else f"nano-banana-{alias}") if fam in GEMINI_IMAGE_ALIAS else None
        buckets[b].append({"family": fam, "alias": alias_name, "bucket": b, "cheapest": offers[0],
                           "min": offers[0].get("cny") if offers[0].get("cny") is not None else offers[0].get("price"), "usd": offers[0].get("price"), "unit": offers[0].get("unit"),  # noqa: E501
                           "count": len(offers), "sites": len({o.get("site") for o in offers}),
                           "variants": var_list, "variant_n": len(var_list)})
    out = []
    for b in BUCKET_ORDER:
        items = buckets.get(b) or []
        items.sort(key=lambda x: (-x["sites"], x["family"]))
        if items:
            out.append({"id": b, "label": BUCKET_LABEL[b], "families": items, "n_families": len(items),
                        "n_offers": sum(x["count"] for x in items)})
    return out


# ---------------- 中转币种 / 汇率 ----------------
def rate_info(status: dict | None) -> dict:
    """从 new-api /api/status 推断充值汇率：price = 充值 1 美元额度所需人民币（new-api 充值页“单价”）。
    显示类型 quota_display_type（USD/CNY/CUSTOM/TOKENS）只影响前台展示，不代表真实花费。"""
    s = status or {}
    disp = s.get("quota_display_type") or ("USD" if s.get("display_in_currency", True) else "TOKENS")
    price = s.get("price")
    out = {"display": disp, "symbol": s.get("custom_currency_symbol") or "", "usd_exchange_rate": s.get("usd_exchange_rate"),
           "topup_price": price, "rmb_per_quota_usd": None, "source": "assumed", "mislabeled": False, "warn": ""}
    if isinstance(price, (int, float)) and 0.03 <= price <= 12:
        out.update(rmb_per_quota_usd=float(price), source="api/status.price")
        if price <= 1.5:
            # ¥≈1 换 $1 额度：页面显示的 “$” 实为人民币成本
            out["mislabeled"] = disp in ("USD", None, "") or s.get("custom_currency_symbol") in ("$",)
            out["currency"] = "CNY≈USD额度"
        else:
            out["currency"] = "USD"
        if price < 0.3: out["warn"] = "充值单价异常低，可能是促销或单位不同，需人工核对"
    else:
        out.update(rmb_per_quota_usd=ASSUME["fallback_rmb_per_usd"], currency="unknown",
                   warn="未公开充值单价，按 ¥7.2/$ 估算")
    return out
