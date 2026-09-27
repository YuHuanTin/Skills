---
name: skills-index
description: skill 根索引，仅作导航，不含子 skill 的具体能力描述
---

# skills-index

工作区所有 skill 的入口。按任务关键词匹配到对应子 skill 后，跳转过去执行。

## 子 skill 速查

| 触发关键词 | 子 skill | 用途摘要 |
|---|---|---|
| 抓网页、下载网页、镜像站点、离线保存、爬站、mirror、offline、http server 本地 | [download_website](download_website/SKILL.md) | 抓取网页 HTML 与所有静态资源到本地，并起一个 `python -m http.server` 提供离线浏览 |
| 逆向、IDA、JEB、JADX、smali、dex、重命名符号、伪代码、反编译、patch、驱动 | [reverse-enginer-skill](reverse-enginer-skill/SKILL.md) | 逆向分析习惯：IDA/JEB/JADX MCP 客户端连接、符号重命名、文档编写规范、辅助脚本 |
| 编程、代码、开发环境、工具链、语言、规范 | [coding](coding/SKILL.md) | 编程相关入口：安装语言、代码风格、代码简化，按子文档表再路由 |

## 路由规则

1. 用户请求里出现上表触发关键词（或近义词）→ 直接加载对应子 skill 的 SKILL.md
2. 不确定时优先问用户：「这个任务是 A 还是 B？」，不要替用户决定
3. 同时命中多个子 skill（如「下载网页并写一个 IDA 脚本分析」）→ 按主任务路由，主任务完成后提示次任务也可用对应 skill
4. 没有命中任何子 skill → 当作普通任务处理，不要强行加载本索引

## 维护

新增 skill 时同步更新本索引的速查表，保持触发关键词与子 skill `description` 一致。