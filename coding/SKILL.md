---
name: coding
description: 编程相关任务的总入口，按子文档表路由到具体主题：Rust 语言、Python、代码风格（编码、布局、注释、测试）、行为不变前提下的代码简化重构。
---

# coding

编程相关任务的总入口。按主题匹配到下表的子文档后，跳转过去执行。

## 子文档

| 主题 | 文档 | 摘要 |
|---|---|---|
| Rust 语言 | [rust.md](rust.md) | 目前只有 Windows 安装（下 rustup-init，用 gnu ABI 免装 MSVC），其余主题待补 |
| Python 语言、形参换行、类型标注、__pycache__、getattr、hasattr | [python.md](python.md) | Python 专属风格（形参换行、类型标注、字节码缓存、防御式成员访问） |
| 代码风格、编码规范、UTF-8 | [code-style.md](code-style.md) | 通用代码风格（编码、布局、注释、测试） |
| 简化、重构可读性、降低复杂度、清理冗余、改写清晰 | [code-simplification.md](code-simplification.md) | 在行为不变前提下简化代码：拆嵌套、合并重复、命名具体、删死代码 |

## 路由规则

1. 用户提到上表主题（或近义词）→ 加载对应子文档执行
2. 没有命中 → 当作普通任务处理，不要强行加载本 skill

## 维护

新增文档时，放在本目录下并同步更新上表。
