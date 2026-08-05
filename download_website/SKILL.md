---
name: download_website
description: Mirror a web page (HTML + every reachable CSS, JS, image, video, font) to a local folder, rewrite references so it works offline, and serve it on a local HTTP server. Use when the user asks to "抓取/下载/镜像整个网页/网站到本地"、"爬取这个页面所有资源"、"保存网页以离线访问"、"把页面下载下来本地打开"、"镜像这个 URL"、"爬站并打包"、or wants a single-command downloader + local HTTP server combo. Triggers on phrases like "完整抓取这个网页到本地"、"下载这个网页和资源"、"做一个离线镜像"、"本地起个服务器访问"等.
---

# download_website

A self-contained offline-mirror tool. Single Python script (stdlib only), no `curl`/`wget` required.

## What you do

When the user asks you to mirror a webpage (or even a small site) to local disk and view it offline:

1. Run the bundled script in **fetch** mode against the URL and an output directory:
   ```
   python <skill-dir>/scripts/download_website.py fetch <URL> <out_dir>
   ```
   The script:
   - downloads the entry HTML using a browser User-Agent,
   - walks `<link href>`, `<script src>`, `<img src>`, `<video src/poster>`, `<source src>`, `srcset`, inline `url(...)` in `<style>` blocks, and `url(...)` inside any downloaded CSS,
   - mirrors site-relative assets under `<out_dir>/<path>`,
   - mirrors CDN fonts/CSS/JS (cdnjs.cloudflare.com, cdn.jsdelivr.net) under `<out_dir>/<cdn-host>/<path>`,
   - strips Cloudflare email-protection helpers, the analytics beacon, and any inline Google Fonts insertion,
   - rewrites every site-relative `/foo` to local `foo`,
   - renames any literal `@` in folder names to `-` (katex@0.16.28 → katex-0.16.28) because Python's `SimpleHTTPRequestHandler` mis-parses `@` as user-info,
   - rewrites FontAwesome CDN URLs inside downloaded CSS to local relative paths,
   - verifies every local URL referenced in the rewritten `index.html` exists on disk.

2. Run the script in **serve** mode so the user can browse the result in a browser:
   ```
   python <skill-dir>/scripts/download_website.py serve <out_dir> [--port 8000]
   ```
   This spawns the standard library `python -m http.server <port> --bind 0.0.0.0 --directory <out_dir>` and waits for it to exit. No custom handler — the user is running `http.server` itself, just with the directory pre-set.

## Output

- `<out_dir>/index.html` — rewritten entry page, ready to be served as the root document.
- `<out_dir>/<site-path>` — every asset the page references.
- Console output: a per-file status table, plus a final "OK all N local files present" line.

## When to use

- The user says "把网页抓下来到本地" / "完整抓取" / "下载并保存" / "mirror this" / "离线保存" / "爬这个页面".
- The user wants to bundle the result as a `.zip` (or `.skill` archive) for sharing.
- The user wants to start a local HTTP server to view the result.

## When NOT to use

- Pure API/data scraping — use a normal HTTP client, no HTML parsing.
- JavaScript-rendered pages (SPA) — the script only mirrors the initial server response. Tell the user a headless browser (Playwright/Puppeteer) would be needed for SPAs.
- Pages behind login — auth tokens / cookies aren't carried.

## Bundled files

- `scripts/download_website.py` — the entire tool. Stdlib only.
- `references/usage.md` — extended usage notes and troubleshooting.

## Notes

- Tested against https://back.engineering/blog/31/07/2026/ on Windows + Python 3.14. Pulled ~10 MB of HTML, CSS, JS, images, videos, and KaTeX assets into a folder that serves correctly over `python -m http.server`.
- Retry policy: 3 attempts with 1 s / 2 s backoff on transient errors. 403/404 are not retried.
- The fetch command exits 0 even when individual resources fail; check the warning summary at the end.