# mooo.si

AI 卡网 / API 中转 / AI 工具 报价聚合门户。静态站 + 定时爬虫（GitHub Actions → GitHub Pages）。

```bash
python -m crawler.run      # 抓取 → site/data/offers.json
python -m pytest           # 测试
python -m http.server -d site 8000
```
方案见 [docs/PLAN.md](docs/PLAN.md)。数据仅供参考，请向原始来源核实。
