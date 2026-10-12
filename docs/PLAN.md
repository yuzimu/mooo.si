# mooo.si 方案

## 定位
收集、筛选 AI 卡网、API 中转、AI 工具价格信息的个人门户。重点分类：GCP $300 试用号、Gemini Pro/Ultra 账号及家庭位、Adobe Firefly 积分、Leonardo、Nano Banana 按张计费生图 API、API 中转、通用 AI 工具。

## 数据源与抓取方式
| 来源 | 方式 | 状态 |
|---|---|---|
| priceai.cc | 官方公开 feed `data.priceai.cc/latest.json` → `snapshot_url`（无需鉴权，约 5 分钟刷新，52 个商品，每个商品 Top5 报价）。robots 禁止 `/api/`；自称 monitor/radar 的 UA 爬 HTML 会返回 429 → **只读 feed** | ✅ 已实现 |
| AIGOOD 价格雷达 / ApiNav | 待确认官方域名与是否有 JSON/SSR 数据（猜测域名可访问，未核实）| 🔍 待调研 |
| oai9 | oai9.com 测试返回 502 | ⚠️ 暂不可用 |
| ldxp / wzyp 卡网 | 有阿里云 ESA 滑块验证的站点**直接跳过**，不强行绕过；无验证的店铺页走 HTML 解析 | ⚠️ 部分 |
| Z2U / G2G / Eldorado | robots.txt 可访问；有 Cloudflare 防护，优先找公开搜索接口，低频抓取 | 🔍 待调研 |
| Telegram 报价 | 不直连 oracle `/opt/tg-collector/messages.db`；由采集器侧导出只读 JSONL，`crawler/adapters/telegram.py` 解析 | 📐 接口已设计 |

## 统一 Schema（crawler/schema.py: Offer）
source, product, category, title, price, currency, seller, url, in_stock, stock, captured_at, tags

## 技术栈（v0.2：服务端站点，不再使用 GitHub Pages）
- Web：FastAPI + Jinja2 服务端渲染，`/api/offers` JSON 接口，`/healthz`
- 存储：SQLAlchemy 2，默认 SQLite（`/data/mooo.db`），可切到服务器已有的 1Panel Postgres
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
遵守 robots 与站点公开 feed 政策；不绕验证码（ESA 滑块站点跳过）；低频请求；页面声明仅供参考。
