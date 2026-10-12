# 参考项目与许可说明

本项目实现均为自写；以下项目用于研究公开接口与平台特征（事实信息，不复制代码）。

| 项目 | 许可 | 用途 / 结论 |
|---|---|---|
| dimthink/PriceAI | PriceAI Source Available License（禁止竞品公开服务）+ 数据政策（禁止复制渠道清单） | 仅阅读；未复用代码与渠道清单 |
| bytedoger/awesome-OpenPrice | OpenPrice 自定义许可（禁止数据聚合类竞品、禁止使用渠道资源） | 未使用其渠道清单作种子 |
| qion888/ldsub2api | Apache-2.0 | 确认链动小铺 shopApi（goodsList/goodsInfo/categoryList）参数；其依赖 WAF 浏览器 cookie 同步与自动滑块——不采用 |
| kirk-y/ai-price-monitor, iKeilo/LdxpM, wubw0508/ldxp, maile456/source-browser, WowJokerH/edge-ldxp-filter | 无许可证（保留所有权利） | 仅阅读；均依赖登录 cookie / 浏览器滑块 / 商户令牌——不采用 |
| miku1130/ldxp-merchant-toolkit | MIT | 商户后台 userscript（需商户登录），不适用于公开采集 |
| Samge0/wzyp-view | MIT | 数据分析前端，无采集代码 |
| Wei-Shaw/sub2api | LGPL-3.0 | 指纹：/api/v1/settings/public；价格/套餐接口需 JWT，故仅做存活监控 |

硬性原则：不做验证码/滑块破解，不使用他人 cookie 或账号令牌。
