"""中转模型归桶与变体合并：国模 / ChatGPT / Claude / Gemini / Grok / 图片 / 视频。"""
import re

BUCKETS = [
    ("image", "图片", re.compile(
        r"image|dall-?e|flux|seedream|jimeng|即梦|imagen|midjourney|banana|stable-?diffusion|"
        r"sdxl|ideogram|recraft|cogview|wanx|kolors|qwen-image|gpt-image|grok-imagine-image", re.I)),
    ("video", "视频", re.compile(
        r"veo|kling|runway|luma|sora|minimax-video|hailuo|vidu|grok-imagine-video|"
        r"seedance|wanx-video|cogvideo", re.I)),
    ("claude", "Claude", re.compile(r"claude|anthropic", re.I)),
    ("gemini", "Gemini", re.compile(r"gemini|imagen", re.I)),  # imagen already image; order matters
    ("grok", "Grok", re.compile(r"\bgrok\b|xai", re.I)),
    ("chatgpt", "ChatGPT", re.compile(r"\bgpt-?\d|o[1-9]\b|o3\b|o4\b|chatgpt|openai|codex|davinci|whisper|tts", re.I)),
    ("china", "国模", re.compile(
        r"deepseek|qwen|chatglm|glm-|doubao|seed-|kimi|moonshot|hunyuan|yi-|yi_|01-ai|"
        r"minimax|abab|baichuan|ernie|wenxin|spark|sensenova|step-|mistral|llama|"  # 常见中文栈+开源常作国模中转
        r"internlm|yi1|skylark|volc|字节|通义|文心|智谱|百川|星火", re.I)),
]

# 变体 → 规范名（先匹配先生效）
CANON = [
    (re.compile(r"^gpt-image-2\.5.*", re.I), "gpt-image-2.5"),
    (re.compile(r"^gpt-image-2($|[-.])", re.I), "gpt-image-2"),
    (re.compile(r"^gpt-image-1\.5.*", re.I), "gpt-image-1.5"),
    (re.compile(r"^gpt-image-1($|[-.])", re.I), "gpt-image-1"),
    (re.compile(r"^dall-?e-3.*", re.I), "dall-e-3"),
    (re.compile(r"^dall-?e-2.*", re.I), "dall-e-2"),
    (re.compile(r"^grok-imagine-image.*", re.I), "grok-imagine-image"),
    (re.compile(r"^grok-imagine-video.*", re.I), "grok-imagine-video"),
    (re.compile(r"^gemini-[\d.]+-flash-?(lite-)?image.*", re.I), "gemini-flash-image"),
    (re.compile(r"^gemini-[\d.]+-pro-image.*", re.I), "gemini-pro-image"),
    (re.compile(r"^gemini-2\.5-flash-image.*", re.I), "gemini-2.5-flash-image"),
    (re.compile(r"^veo.*", re.I), "veo"),
    (re.compile(r"^kling.*", re.I), "kling"),
    (re.compile(r"^flux.*", re.I), "flux"),
    (re.compile(r"^doubao-seedream.*|seedream.*", re.I), "seedream"),
    (re.compile(r"^qwen-image.*", re.I), "qwen-image"),
    (re.compile(r"^claude-(opus|sonnet|haiku).*", re.I), lambda m: f"claude-{m.group(1).lower()}"),
    (re.compile(r"^claude-3-5-sonnet.*|^claude-3\.5-sonnet.*", re.I), "claude-sonnet"),
    (re.compile(r"^claude-3-opus.*", re.I), "claude-opus"),
    (re.compile(r"^claude-3-haiku.*", re.I), "claude-haiku"),
    (re.compile(r"^gemini-[\d.]+-pro.*", re.I), "gemini-pro"),
    (re.compile(r"^gemini-[\d.]+-flash-lite.*", re.I), "gemini-flash-lite"),
    (re.compile(r"^gemini-[\d.]+-flash.*", re.I), "gemini-flash"),
    (re.compile(r"^gpt-4o-mini.*", re.I), "gpt-4o-mini"),
    (re.compile(r"^gpt-4o(?!-mini).*", re.I), "gpt-4o"),
    (re.compile(r"^gpt-4\.1-mini.*", re.I), "gpt-4.1-mini"),
    (re.compile(r"^gpt-4\.1-nano.*", re.I), "gpt-4.1-nano"),
    (re.compile(r"^gpt-4\.1(?!-).*|^gpt-4\.1$", re.I), "gpt-4.1"),
    (re.compile(r"^gpt-4-turbo.*|^gpt-4(?!o).*", re.I), "gpt-4"),
    (re.compile(r"^gpt-5\.[\d]+.*|^gpt-5(?!-)|^gpt-5-", re.I), "gpt-5"),
    (re.compile(r"^gpt-3\.5.*", re.I), "gpt-3.5-turbo"),
    (re.compile(r"^o3-mini.*", re.I), "o3-mini"),
    (re.compile(r"^o3(?!-).*|^o3$", re.I), "o3"),
    (re.compile(r"^o1-mini.*", re.I), "o1-mini"),
    (re.compile(r"^o1(?!-).*|^o1$", re.I), "o1"),
    (re.compile(r"^deepseek-r1.*", re.I), "deepseek-r1"),
    (re.compile(r"^deepseek-v3.*|^deepseek-chat.*|^deepseek-v4.*", re.I), "deepseek-v3"),
    (re.compile(r"^deepseek.*", re.I), "deepseek"),
    (re.compile(r"^qwen.*", re.I), "qwen"),
    (re.compile(r"^glm-4.*|^chatglm.*", re.I), "glm-4"),
    (re.compile(r"^doubao.*|^seed-.*", re.I), "doubao"),
    (re.compile(r"^kimi.*|^moonshot.*", re.I), "kimi"),
    (re.compile(r"^hunyuan.*", re.I), "hunyuan"),
    (re.compile(r"^grok-2.*", re.I), "grok-2"),
    (re.compile(r"^grok-3.*", re.I), "grok-3"),
    (re.compile(r"^grok.*", re.I), "grok"),
]

BUCKET_ORDER = ["chatgpt", "claude", "gemini", "grok", "china", "image", "video", "other"]
BUCKET_LABEL = {b: lab for b, lab, _ in BUCKETS} | {"other": "其他"}


def family_of(name: str) -> tuple[str, str]:
    """返回 (bucket_id, canonical_family_name)。"""
    n = (name or "").strip()
    # strip vendor prefixes like 熊猫特供-按量-SSS-
    n2 = re.sub(r"^[^a-z0-9]*", "", n, flags=re.I)
    n2 = re.sub(r"^(熊猫[^a-z]*|按量-?|满血[^a-z]*|特供[^a-z]*|S+-?)+", "", n2, flags=re.I)
    base = n2 or n
    # bucket: image/video first
    bucket = "other"
    for bid, _lab, rx in BUCKETS:
        if rx.search(base) or rx.search(n):
            bucket = bid
            break
            # gemini imagen already caught by image if image first - imagen in image pattern
    # canonical
    canon = base.lower()
    for rx, repl in CANON:
        m = rx.match(canon) or rx.match(base)
        if m:
            canon = repl(m) if callable(repl) else repl
            break
    else:
        # strip date/hash suffixes: -20241022, -preview, -c
        canon = re.sub(r"[-_](preview|latest|exp|thinking|c)$", "", canon, flags=re.I)
        canon = re.sub(r"[-_]\d{6,8}$", "", canon)
        canon = re.sub(r"[-_]20\d{6}$", "", canon)
    # fix bucket if canon is clearly image but name missed
    if bucket == "gemini" and "image" in canon:
        bucket = "image"
    if bucket == "grok" and "imagine-image" in canon:
        bucket = "image"
    if bucket == "grok" and "imagine-video" in canon:
        bucket = "video"
    return bucket, canon


def group_models(rows: list[dict]) -> list[dict]:
    """rows: {model, price, unit, site, ...} → bucket → families with cheapest + variants."""
    from collections import defaultdict
    fams = defaultdict(list)
    for r in rows:
        b, fam = family_of(r.get("model") or "")
        fams[(b, fam)].append(r)
    buckets = defaultdict(list)
    for (b, fam), offers in fams.items():
        offers = [o for o in offers if o.get("price") and o["price"] > 0]
        if not offers: continue
        offers.sort(key=lambda x: (x["price"], x.get("unit") or ""))
        # variants = distinct raw model names
        variants = {}
        for o in offers:
            variants.setdefault(o["model"], []).append(o)
        var_list = []
        for vn, vo in variants.items():
            vo.sort(key=lambda x: x["price"])
            var_list.append({"name": vn, "min": vo[0]["price"], "unit": vo[0].get("unit"),
                             "count": len(vo), "cheapest": vo[0], "offers": vo[:15]})
        var_list.sort(key=lambda x: x["min"])
        buckets[b].append({
            "family": fam, "bucket": b, "label": BUCKET_LABEL.get(b, b),
            "min": offers[0]["price"], "unit": offers[0].get("unit"),
            "count": len(offers), "sites": len({o.get("site") for o in offers}),
            "cheapest": offers[0], "variants": var_list, "variant_n": len(var_list),
        })
    out = []
    for b in BUCKET_ORDER:
        items = buckets.get(b) or []
        items.sort(key=lambda x: (x["min"], -x["sites"]))
        if items:
            out.append({"id": b, "label": BUCKET_LABEL.get(b, b), "families": items,
                        "n_families": len(items), "n_offers": sum(x["count"] for x in items)})
    return out
