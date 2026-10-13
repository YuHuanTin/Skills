---
name: jadx
description: jadx + jadx-mcp 客户端连接、传参写法、rename 流程
---

# jadx

> 配置
如果没有配置 mcp，则添加后重启
```
"jadx-mcp": {
  "type": "http",
  "url": "http://127.0.0.1:8651/mcp"
}
```
>

连接 jadx mcp 用 jadx_mcp_server.py。每次写操作后必须等缓存刷新再继续；批量操作须写脚本、插入延迟、用后即删。

## 传参写法

一律用当前显示名，不用 dex 旧名，jadx 源码顶部出现 `/* JADX INFO: renamed from: 旧全限定名 */` 即已改名。此后 `get_*`/`rename_*` 的 `class_name`/`method_name` 必须用新名(例 `g1`→`MMAutoAuth`、`e`→`sendImp`)。`get_method_by_name` 的 `decl` 字段是旧 dex 签名，禁止用于寻址

| 工具 | 必传 | 硬规则 |
|------|------|--------|
| `rename_class` | `class_name`(全限定 `com.a.B.foo`)、`new_name`(不含包) | |
| `rename_method` | `method_name`(全限定)、`new_name` | 有重载或大小写同名(`k`/`K`)必传 `method_signature`；签名只传 dex 描述符 `(Lcom/a/z0;)I` 格式 |
| `rename_field` | `class_name`(全限定)、`field_name`、`new_name` | |
| `rename_variable` | `class_name`(全限定)、`method_name`(裸名 `onCreate`)、`variable_name`、`new_name` | 局部变量和形参都能改；每次仅改一个，改完立即 `get_method_by_name` 取剩余变量当前显示名 |

- `@Override` 方法：rename 主绑定接口/父类，即源码 `@Override // A, B` 里列的第一个类型。改主绑定即传播到所有实现类；改前先 `get_method_by_name` 看 `@Override //` 首个类型。字段同理改声明方

## rename_variable 的 variable_name 取法

显示名 = 内部基名 + 尾部寄存器/序号

`variable_name` 传法：
1. 显示名不以纯数字结尾(`z0Var`/`o0Var`/`iK`)→ 直接传完整显示名，通常无需 `reg`
2. 显示名以数字结尾(`i16`/`th6`)→ 去掉尾部数字传基名(`i16`→`i`，`th6`→`th`)。改后新名仍会被加回 reg 号显示(`th`→显示`ex6`)
3. 基名有歧义(多个同基名变量，如多个 `i` 开头 int)→ 基名+`reg`(smali 寄存器号)消歧。寄存器号算法：`.registers R`、共 `P` 个参数(窄类型各占 1 寄存器)，则第 `N` 个参数(N 从 1 计，static 方法首参即 N=1)的寄存器 = `v(R - P + N - 1)`。例：`sendImp` 第 4 参数、R=13、P=4 → `v12` → `variable_name="i"` + `reg=12`；`d` 第 3、4 参数、R=11、P=5 → `v8`/`v9` → `reg=8`/`reg=9`。显示名尾数字不是 reg，且改掉一个后剩余同基名变量的显示名尾数字会变，使用 reg 稳定定位
4. 失败时依次排查：显示名是否被重编号(重拉源码)→ 是否该去尾数字取基名 → 是否需加 `reg` → `clear_cache` 后重试。禁止把完整显示名 `i16` 或 smali 名 `p3`/`v12` 直接当 `variable_name`
