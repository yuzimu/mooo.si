# mooo.si 方案

## 定位
收集、筛选 AI 卡网、API 中转、AI 工具价格信息的个人门户。重点分类：GCP $300 试用号、Gemini Pro/Ultra 账号及家庭位、Adobe Firefly 积分、Leonardo、Nano Banana 按张计费生图 API、API 中转、通用 AI 工具。

## 数据源与抓取方式
| 来源 | 方式 | 状态 |
|---|---|---|
| priceai.cc | 官方公开 feed `data.priceai.cc/latest.json` → `snapshot_url`（无需鉴权，约 5 分钟刷新，52 个商品，每个商品 Top5 报价）。robots 禁止 `/api/`；自称 monitor/radar 的 UA 爬 HTML 会返回 429 → **只读 feed** | ✅ 已实现 |
| AIGOOD 价格雷达 / ApiNav | 待确认官方域名与是否有 JSON/SSR 数据（猜测域名可访问，未核实）| 🔍 待调研 |
| oai9 | oai9.com 测试返回 502 | ⚠️ 暂不可用 |
| ldxp / wzyp 卡网 | ShopApi 是公开 JSON 接口（无需登录、无验证码），可直采：www.ldxp.cn / wzyp.cn 直接返回 `code:1`。pay.ldxp.cn、ldxp.cn 已 301 到 wzyp.cn，抓取时**不跟随跳转**、按域名故障转移（跟随跳转会丢 POST body，被误判成"店铺链接不存在"）| ✅ 已实现 |
| Z2U / G2G / Eldorado | robots.txt 可访问；有 Cloudflare 防护，优先找公开搜索接口，低频抓取 | 🔍 待调研 |
| Telegram 报价 | 不直连 oracle `/opt/tg-collector/messages.db`；由采集器侧导出只读 JSONL，`crawler/adapters/telegram.py` 解析 | 📐 接口已设计 |

## 统一 Schema（crawler/schema.py: Offer）
source, product, category, title, price, currency, seller, url, in_stock, stock, captured_at, tags

## 技术栈（v0.2：服务端站点，不再使用 GitHub Pages）
- Web：FastAPI + Jinja2 服务端渲染，`/api/offers` JSON 接口，`/healthz`
- 存储：**MongoDB 单库**（见下文“存储选型”）
- 调度：APScheduler 进程内定时任务（默认 30 分钟），每次运行记录 `crawl_runs`
- 适配器层：`app/adapters/*`，每源 `fetch() -> Iterable[Offer]`，声明 `use_proxy` / `use_browser`
- 网络层 `app/net.py`：代理池（PROXY_POOL_URL / PROXY_LIST 轮换）+ 指纹浏览器 CDP 钩子（BROWSER_CDP_URL，Playwright connect_over_cdp）
- 质量：ruff + pytest；Docker + docker-compose

## 部署
目标：用户的 Oracle 服务器（140.245.91.120，Oracle Linux 9.8，aarch64，4 核 / 22G，Docker 29 + Compose v5）。
- 80/443 由 1Panel 的 OpenResty 占用（已有 site-mooo-* 等站点），因此**不另起 Caddy/nginx**：容器只绑 `127.0.0.1:8790`，在 1Panel 新建 mooo.si 反代站点并申请证书。
- 已占用的本地端口：2260, 5432, 6080, 6379, 8000, 8088, 8317, 8788, 38001-38005, 18080（1Panel）——8790 空闲。
- 镜像由 GitHub Actions 构建 arm64/amd64 推送 GHCR，SSH 到服务器 `/opt/mooo-si` 执行 `docker compose pull && up -d`。
- 服务器上已有可能可复用的服务（未改动、未深查）：`x2api-resin`（ghcr.io/resinat/resin，疑似代理池，127.0.0.1:2260）、`x2api-browser`（127.0.0.1:6080，疑似浏览器/noVNC）。确认后可填入 PROXY_POOL_URL / BROWSER_CDP_URL。
- 备选：无 1Panel 时用 `deploy/Caddyfile` 自动 HTTPS。

## 合规
遵守 robots 与站点公开 feed 政策；不绕验证码（ESA 滑块站点跳过）；低频请求；页面声明仅供参考。链动小铺只调用店铺页前端自身也在调的公开 ShopApi JSON 接口（无验证码、无登录）：不破解滑块、不伪装搜索引擎身份；`LDXP_UA` 仅用于避开 ESA 对 httpx 库默认 UA 的机器指纹封锁。

## 线上现状（2026-10-12 部署）
- `/opt/mooo-si`：docker-compose.yml（镜像 ghcr.io/yuzimu/mooo.si:latest，首个版本在服务器本机构建并打此标签）、`.env`（600 权限）、`data/mooo.db`、`src/`（构建源码）。
- 1Panel OpenResty：`/opt/1panel/www/conf.d/site-mooo-si.conf` + `/opt/1panel/www/sites/site-mooo-si/`，仿照 site-mooo-grok（Cloudflare 真实 IP / 来源白名单 / http→https）。改动前备份在 `/opt/mooo-si/conf.d-backup-*.tgz`。注意：该站点为手写配置，1Panel 网站列表里不会显示。
- 证书：acme.sh（docker）webroot 签发 Let's Encrypt，`/etc/cron.d/mooo-si-cert` 每日续期并重载 openresty。
- MongoDB：计划经 1Panel 应用商店安装（127.0.0.1、认证、库 mooo + 用户 mooo）。\n- 代理池：未接入（resin 需要代理令牌，属于 x2api 的凭据，未复用）。

## 存储选型（v0.3）
只用 MongoDB，**不再使用 SQLite/Postgres**。理由：当前结构化数据只有「标准化报价 + 抓取记录」两张表，没有跨表事务或复杂关联；
各来源字段差异大（priceai 的 min_order/expires_at、未来 TG 消息、海外平台的卖家评分等），放进文档的 `extra` 与 `raw` 更自然；
单一数据库也降低运维成本。等出现用户体系、订阅提醒、价格历史聚合报表等强关系需求时，再引入 1Panel 已有的 Postgres。

集合：
- `raw`：每次抓取的原始 payload（`source, fetched_at, payload`），TTL 索引默认保留 14 天（RAW_RETENTION_DAYS）。
- `offers`：标准化报价 + `extra`（来源特有字段）+ `kw`（搜索关键词数组）；每个来源保留最新快照。
- `crawl_runs`：抓取记录（source, started_at, count, error）。
- 预留 `tg_messages`：TG 采集器导出的消息原文。

索引：`(category, in_stock, price)`、`(source, price)`、`(product, price)`、`price`、`kw`（多键）、`raw(source, fetched_at)`、`raw.fetched_at` TTL。

中文搜索：Mongo 自带 text 索引不支持中文分词，因此写入时对 product/title/seller/tags 做归一化（小写、全角斜杠等），
生成 CJK 单字 + 双字 n-gram、英文/数字整词及前缀，存入 `kw`；查询时 CJK 取双字、英文取整词，用 `$all` 命中多键索引。
支持 `/api/search?q=&category=&source=&in_stock=&min_price=&max_price=&sort=price|-price|new&limit=&offset=`，页面 `/search` 同样走 Mongo。

## v0.5 两阶段管线（发现 → 定向抓取）
每 2 小时一轮（cron `*/2:07` + 0–10 分钟抖动），流程：代理检查（fail closed）→ 聚合源适配器 → 阶段一发现 → 阶段二定向抓取 → 跨源去重。

### 阶段一：发现（`app/discovery/`，可插拔 `DiscoverySource.discover() -> (url, type_hint, context, seen_at)`）
| 渠道 | id | 频率 | 说明 |
|---|---|---|---|
| 聚合站报价链接 | offers | 每轮 | priceai / aigood / apinav cards / kawanghub 商品链接与店铺链接 |
| ApiNav 中转目录 | apinav-sites | 12h | 162 个中转站 targetUrl |
| kawanghub 店铺 | kawanghub-shops | 12h | 679 店铺 + 店铺 TG |
| TG 采集器 | tg-collector | 每轮 | `/opt/tg-collector/messages.db` 只读（`mode=ro&immutable=1`），提取 URL / t.me / 店铺链接 |
| TG 公开频道预览 | tg-preview | 24h | `t.me/s/<name>`，群组 302 自动跳过并标记 private |
| GitHub 列表 | github-lists | 24h | GITHUB_LIST_URLS 中的 awesome Markdown |
| 搜索引擎指纹 | search | 24h | Brave API（需 BRAVE_API_KEY），查询 New API 页脚、catfk/ldxp 店铺 |

规范化：`catfk:<token>` / `ldxp:<token>`（店铺）、`catfk:item:<key>`（抓取时解析为店铺后合并）、`tg:<name>`、`web:<host>`。
`targets` 集合字段：type(relay/card_shop/tg/unknown)、platform、url、sources{渠道: 次数}、mentions、first_seen/last_seen、status、fp、health、history(最近 10 次)、priority。

### 阶段二：定向抓取（`app/platforms/`）
- 指纹：`/api/status`（new-api/one-api）、HTML 特征（shopApi=链动系、dujiaoka、acg-faka）、ESA/阿里云验证 → blocked_captcha、CF 挑战 → blocked_cf、5xx/超时 → down。指纹 7 天内复用。
- 适配器：**catfk**（`/shopApi/Shop/goodsList` JSON，每目标 ≤5 页）、**new-api/one-api**（`/api/pricing` JSON；重点模型写 offers，完整表写 `relay_prices`；304 视为未变化）。
- ldxp/微店云铺：ShopApi 公开可直采（无需登录、无验证码）；pay.ldxp.cn / ldxp.cn 已迁移，抓取不跟随 3xx、按域名故障转移（www.ldxp.cn → wzyp.cn → pay.ldxp.cn → ldxp.cn）。注意阿里云 ESA 的 `http_bot_simple` 规则会拦 httpx 库默认 UA，故请求显式固定 UA（`LDXP_UA` 可覆盖）；实测 `X-Real-IP` 对放行与否**无影响**。
- 调度：priority = log2(提及)×10 + 新鲜度 + 渠道数×3；6 小时内成功抓过的目标跳过；每轮 ≤120 个目标。
- 带宽与并发：全局 4 并发、同域名串行 + 2s 间隔；GET 自动 ETag/If-Modified-Since（`http_cache`），304 复用缓存正文；只抓 JSON/HTML 不下载资源；浏览器模式屏蔽 image/media/font/stylesheet；每轮写 `pipeline_runs.result.traffic`（字节、请求数、304 数、Top 域名）。
- 代理：**所有抓取流量强制走 resin 代理池**（`PROXY_REQUIRED=1`，账号 `Default.mooo`），代理不可用则整轮停止。
- 去重：`dedupe_key = host+path`；直连抓到的（catfk/relay）优先，聚合源中同链接报价标记 `dup`，聚合源之间同链接只保留最新一条。

### 下一步渠道
linux.do 公开帖（Cloudflare 403，需 CDP 浏览器 + 代理）、16688.com.cn 等卡网平台适配、独角数卡/异次元 商品页解析、FOFA/Hunter 指纹测绘、更多导航站（如 ai-bot.cn、各类 API 中转导航）、TG 频道更多公开预览。
