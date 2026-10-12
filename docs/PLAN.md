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

## 技术栈
- 爬虫：Python 3.12 标准库（后续按需加 httpx / selectolax），每源一个 Adapter（`fetch() -> Iterable[Offer]`）
- 前端：纯静态 HTML+JS，读取 `data/offers.json`，支持搜索/分类/有货筛选/价格排序
- 后续：历史价格存 SQLite/JSON 快照，价格走势图

## 部署
GitHub Actions 每 30 分钟抓取 → 发布到 GitHub Pages，`site/CNAME`=mooo.si。域名 DNS：mooo.si 加 A 记录指向 GitHub Pages IP（185.199.108–111.153）或 CNAME 到 `<user>.github.io`。需抓取受限源时再加一台小 VPS 跑爬虫推送数据。

## 合规
遵守 robots 与站点公开 feed 政策；不绕验证码；低频请求；页面声明仅供参考。
