---
name: unity
description: Unity AssetBundle、Addressables catalog 资源处理
---

# Unity 资源处理

本文档记录 Unity AssetBundle、Addressables catalog 资源替换所需的工具。记录日期为 2026-10-03，项目星标与提交日期来自 GitHub 页面。

## 工具清单

| 项目 | 语言 | 用途 | Stars | 最近提交 |
|---|---|---|---:|---|
| [UnityPy](https://github.com/K0lb3/UnityPy) | Python | 读取、修改、保存 Unity assets 与 AssetBundle | 1.5k | 2026-10-03 |
| [AssetsTools.NET](https://github.com/nesrak1/AssetsTools.NET) | C# | 读取、修改、写入 SerializedFile 与 AssetBundle | 691 | 2026-09-10 |
| [AddressablesTools](https://github.com/nesrak1/AddressablesTools) | C# | 处理 Addressables JSON、BIN、`catalog.bundle`，提供 `patchcrc` | 146 | 2026-08-09 |
| [UABEANext](https://github.com/nesrak1/UABEANext) | C# | GUI 修改 SerializedFile 与 AssetBundle | 410 | 2026-07-27 |
| [UABEA](https://github.com/nesrak1/UABEA) | C# | GUI 修改较新 Unity 版本的 SerializedFile 与 AssetBundle | 2.4k | 2026-05-11 |
| [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit) | Python | CLI/GUI 打包与替换 Blue Archive Bundle 资源 | 63 | 2026-10-01 |
| [UnityCN-Helper](https://github.com/AXiX-official/UnityCN-Helper) | C# | UnityCN AssetBundle 加密、解密与文件夹批处理 | 58 | 2026-02-25 |

## 工具选择

`UnityPy` 适合用 Python 读取 Bundle，修改 `Texture2D`、`TextAsset` 等对象，再保存为新的 Bundle 文件。

`AddressablesTools` 用于处理 Addressables 生成的 catalog 文件。UnityPy 保存 Bundle 后，catalog 中的路径、Hash 或 CRC 可能需要同步调整。

`UnityCN-Helper` 仅在目标 Bundle 使用 UnityCN 保护时加入流程。它负责解密和加密文件，资源对象的修改仍由 UnityPy 完成。

`AssetsTools.NET`、`UABEA` 和 `UABEANext` 适合 C# 项目或需要 GUI 操作的场景。`BA-Modding-Toolkit` 的 `pack` 命令已经封装资源替换和 Bundle 保存，但功能围绕 Blue Archive 的文件命名与目录规则设计。
