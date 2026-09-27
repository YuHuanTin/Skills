---
name: python-skill
description: Python 专属代码风格（形参换行、类型标注、字节码缓存、防御式成员访问）
---

# Python

形参不换行，尽可能写在同一行；空行数量用 1，不用 2

返回值类型是 None 就不标注；不用 `__all__` 暴露函数

使用 `-B` 或设置 `PYTHONDONTWRITEBYTECODE=1` 运行，发现已有 __pycache__ 时删除

## 成员访问

- 禁止使用 `getattr(..., default)`、`hasattr()` 等防御式成员访问。所有正式成员必须直接访问；缺失成员应立即抛出异常，不编写强行兜底代码
