---
name: ida
description: IDA / idalib-mcp 连接、超时、结构体与 CFG 导出
---

# ida

## 连接选择

1. 检查当前会话是否存在原生 IDA MCP tools，并调用 `idb_list` 确认连接可用，可用时直接使用，不额外启动服务
2. 原生 IDA MCP 不存在或无法连接时，后台启动 `idalib-mcp --host 127.0.0.1 --port 8745 --unsafe`，等待就绪后继续，任务结束时不关闭；`--unsafe` 必须在启动 `idalib-mcp` 时传入
3. 使用 venv Python 运行 [scripts/using_mcp.py](../scripts/using_mcp.py) 调用 HTTP tool

放宽 ida 操作的超时时间

在确定的情况下可新建对类、常见结构、可能有助于分析的结构的结构体类型，对变量进行类型设置后帮助分析

ida 批量重命名函数后创建一个函数分组，将原来的函数移动到分组内，注意是剪贴而不是复制一份

用户如需获取 ida 函数 CFG 则使用 `idaapi.gen_flow_graph_ea`，传入 `idaapi.CHART_GEN_DOT`，输出紧凑 `.dot` 文件
