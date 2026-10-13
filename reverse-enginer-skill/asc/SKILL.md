---
name: asc
description: droidasc — Android APK 反编译 CLI / Tk GUI (https://github.com/MG1937/ASC)
---

# droidasc

## 安装

venv 环境安装

```bash
pip install droidasc
```

## 子命令

| 命令 | 作用 |
|---|---|
| `droidasc getclass <apk> <class>` | 反编译指定类；类名支持 `Lcom/foo/Bar;` 与 `com.foo.Bar` 两种；`-o FILE` 写文件；`--threads N` 改工作线程数 |
| `droidasc listclass <apk>` | 列全部类描述符；`--prefix PREFIX` 过滤；`-o FILE` 写文件 |
| `droidasc getmanifest <apk>` | 解码 AndroidManifest.xml；`-o FILE` 写文件 |
| `droidasc findrefs <apk> <kind> <value>` | 跨 DEX 搜引用；`kind` ∈ `string` / `type` / `method` / `field`；`method`/`field` 支持 `--class NAME` + `--fuzzy-class` 限定类 |
| `droidasc <apk> --gui` | 启动 Tk 界面 |

## 示例

```bash
droidasc getclass app.apk com.foo.Main -o Main.java
droidasc listclass app.apk --prefix com.foo -o classes.txt
droidasc getmanifest app.apk -o AndroidManifest.xml
droidasc findrefs app.apk string token
droidasc findrefs app.apk method onCreate --class com.foo.Main
droidasc findrefs app.apk field apiKey
```