---
name: rust-skill
description: Rust 语言技能。目前覆盖 Windows 上的安装（rustup-init + gnu ABI 免装 MSVC），其余主题待补。
---

# Rust

## 安装（Windows）

### 下载

从 `https://rust-lang.org/learn/get-started/` 下载 `rustup-init.exe`

### 安装

```
set RUSTUP_HOME=指定地址
set CARGO_HOME=指定地址
rustup-init.exe -y --no-modify-path --default-host x86_64-pc-windows-gnu
```

| 参数 | 作用 |
|---|---|
| `RUSTUP_HOME` / `CARGO_HOME` | 不指定会装到 `%USERPROFILE%\.rustup` 和 `%USERPROFILE%\.cargo` |
| `-y` | 非交互，跳过确认 |
| `--no-modify-path` | 不改注册表 PATH |
| `--default-host x86_64-pc-windows-gnu` | 用 gnu ABI，不安装 msvc toolchain |

### 安装后写 startup.bat

装完要在 `RUSTUP_HOME` 和 `CARGO_HOME` 的上一级目录写一个 `startup.bat`。`.cargo\bin\` 里的 `cargo.exe`、`rustc.exe` 等全部是指向 `rustup.exe` 的硬链接，它们只读 `RUSTUP_HOME` 和 `CARGO_HOME` 环境变量来定位工具链，读不到就退回 `%USERPROFILE%\.rustup`，结果找不到工具链。

```bat
@echo off
rem Portable Rust toolchain launcher
rem No argument: open an interactive shell with the environment injected
rem With argument: run that command inside the injected environment

set "RUST_ROOT=%~dp0"
set "RUSTUP_HOME=%RUST_ROOT%.rustup"
set "CARGO_HOME=%RUST_ROOT%.cargo"
set "PATH=%CARGO_HOME%\bin;%PATH%"

if not "%~1"=="" goto run
cmd /k
goto :eof

:run
%*
```

`startup.bat cargo build` 直接在该环境下跑一条命令；不带参数进入已注入环境的命令行。

### 卸载

```
rustup self uninstall
```
