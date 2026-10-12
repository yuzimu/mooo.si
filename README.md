# mooo.si

AI 卡网 / API 中转 / AI 工具 报价聚合门户。FastAPI + Jinja2（Tailwind/Alpine 前端）+ MongoDB + APScheduler 定时爬虫，Docker 部署在自有服务器。

## 本地开发
```bash
docker compose --profile dev up -d mongo   # 本地 Mongo
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && pytest -q
python -m app.crawler                       # 手动抓一次
uvicorn app.main:app --reload               # http://127.0.0.1:8000  /search  /api/search  /api/offers  /healthz
```

## 配置（.env，见 .env.example）
| 变量 | 说明 |
|---|---|
| MONGO_URL / MONGO_DB | MongoDB 连接串与库名（测试可用 `mongomock://`） |
| RAW_RETENTION_DAYS | 原始数据保留天数，默认 14 |
| CRAWL_INTERVAL_MIN | 抓取间隔（分钟），默认 30 |
| PROXY_POOL_URL / PROXY_LIST | 代理池：URL 每行一个代理，或逗号分隔列表；适配器 `use_proxy=True` 时轮换使用 |
| BROWSER_CDP_URL | 指纹浏览器 CDP 端点，`app.net.browser_page()` 通过 Playwright `connect_over_cdp` 接入 |

## 部署（Oracle 服务器 + 1Panel OpenResty）
0. 1Panel 应用商店安装 MongoDB：端口仅 127.0.0.1，开启认证；创建库 `mooo` 及用户 `mooo`（readWrite），填入 `.env` 的 MONGO_URL。
1. 服务器：`sudo mkdir -p /opt/mooo-si && cd /opt/mooo-si`，放入 `docker-compose.yml` 和 `.env`。
2. 若 GHCR 镜像为私有：`sudo docker login ghcr.io`（PAT 需 read:packages），或在 GitHub 把包设为 public。
3. `sudo docker compose pull && sudo docker compose up -d`，服务以 host 网络监听 `127.0.0.1:8790`。
4. HTTPS：1Panel → 网站 → 创建反向代理站点 `mooo.si` → `http://127.0.0.1:8790` → 申请 Let's Encrypt 证书（参考 `deploy/openresty-mooo.si.conf`）。不用 1Panel 时可用 `deploy/Caddyfile`。
5. CI/CD：`.github/workflows/ci.yml`（ruff + pytest）、`deploy.yml`（构建 arm64/amd64 镜像推 GHCR → SSH 执行 compose pull/up）。需配置 Secrets：`SERVER_HOST`、`SERVER_USER`、`SERVER_SSH_KEY`。

> 如果工作流未出现在 `.github/workflows/`，说明推送 token 缺少 `workflow` 权限：执行 `gh auth refresh -s workflow` 后把 `deploy/workflows/*.yml` 复制过去再推。

数据仅供参考，请向原始来源核实。方案见 [docs/PLAN.md](docs/PLAN.md)。
