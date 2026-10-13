---
name: web-access
description: eze-is/web-access skill + 本地浏览器启动参数
---

## 安装（仅作一次）

克隆到本 skill 目录的 `scripts/` 子目录下：

```bash
git clone https://github.com/eze-is/web-access web-access/scripts
```

仅需 Node.js 22+, 无需 `npm install` 等额外步骤

调用脚本使用绝对路径：

```bash
node web-access/scripts/check-deps.mjs
node web-access/scripts/proxy-maintenance.mjs status
```

## 启动方法（绕开授权弹窗）

```bash
# Chrome
"<path-to-chrome>\chrome.exe" \
    --remote-debugging-port=9222 \
    --remote-allow-origins=* \
    --user-data-dir="<isolated-profile-path>" \
    about:blank

# Edge
"<path-to-edge>\msedge.exe" \
    --remote-debugging-port=9222 \
    --remote-allow-origins=* \
    --user-data-dir="<isolated-profile-path>" \
    about:blank
```

要点：
- `--remote-debugging-port=9222`：CDP Proxy 默认端口，改端口需同步 `WEB_ACCESS_CDP_PORT`
- `--remote-allow-origins=*`：Chrome 111+ 必需，否则 WebSocket 升级被拒
- `--user-data-dir`：用**专用隔离目录**，默认当前文件同级 `.web-access-profile` 文件夹
- `about:blank` 起点：便于 Proxy 接管，避免一启动就拉到上次会话
- Windows 路径含空格必须用双引号
- 端口占用检查：`netstat -ano | findstr :9222`

## 已知问题：Chrome 134+ UUID 要求

Chromium 134 之后，浏览器级 WebSocket 端点 `/devtools/browser` 在不带 UUID 后缀时会被拒，错误信息为 `Received network error or non-101 status code`。`web-access` 的 `cdp-proxy.mjs` 在拿到 `DevToolsActivePort` 文件时会读出第二行的完整路径，但当文件缺失（CentBrowser 134 在 `about:blank` 启动时不写入该文件）而走手动端口兜底（`findFallbackPort`）时，`wsPath` 为空，最终构造出的 URL 是 `ws://127.0.0.1:9222/devtools/browser`，连接失败。

临时解决：

1. 从浏览器 HTTP API 拿到 UUID：

   ```bash
   curl -s http://127.0.0.1:9222/json/version | grep -oE '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
   ```

2. 把端口与带 UUID 的 WebSocket 路径写入对应浏览器的 `DevToolsActivePort` 路径（以 Chromium 为例）：

   ```bash
   UUID=$(curl -s http://127.0.0.1:9222/json/version | grep -oE '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' | head -1)
   mkdir -p "%LOCALAPPDATA%/Chromium/User Data"
   printf "9222\n/devtools/browser/%s\n" "$UUID" > "%LOCALAPPDATA%/Chromium/User Data/DevToolsActivePort"
   ```

3. 重启 `cdp-proxy`（先 `proxy-maintenance.mjs stop` 再 `check-deps.mjs`），之后 proxy 会用带 UUID 的 URL 连接