#!/usr/bin/env python3
"""单文件离线网站镜像工具。

用法：
    python download_website.py fetch <URL> <out_dir>
        # 把页面及全部可访问的引用资源下载到 out_dir

    python download_website.py serve <site_dir> [--port 8000]
        # 以 site_dir 为根目录启动 `python -m http.server`，绑定 0.0.0.0

功能：
- 仅用标准库和浏览器 User-Agent 获取入口 HTML，不依赖 curl/wget。
- 从 href、src、poster、srcset、url() 以及 <video>/<source> 中发现资源。
- 站内相对路径写到 out_dir/<path>，字体、CSS、JS 等 CDN 资源写到
  out_dir/<cdn-host>/<path>。
- 下载每项资源，暂时性错误使用指数退避重试。
- 从保存的 HTML 中移除 Cloudflare 邮箱保护、分析信标及 Google Fonts 外链注入，
  使页面不再尝试联网。
- 把站内绝对路径 "/foo/bar" 改写为 "foo/bar"，使其能从根页面 index.html 解析。
- 引用 KaTeX 时下载其资源和 CSS 所引用的外部字体；目录名中的 ``@`` 改为 ``-``，
  避免 Python SimpleHTTPRequestHandler 把百分号编码后的 URL 当作用户信息。
- 改写下载样式表中指向 cdnjs.cloudflare.com 的 FontAwesome 字体地址。
- 下载后列出结果 HTML 的本地相对 URL，并验证对应磁盘文件存在。
- ``serve`` 子命令只负责以正确参数启动标准库 HTTP 服务，不实现自定义处理器。

说明：
- 已在 Windows 10 与 Python 3.14 上测试，只使用标准库。
- HTML 相对 URL 以入口 URL 为基准解析，因此 /css/x.css 中的
  "../images/foo.png" 也能落到正确位置。
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Iterable

# ---------------------------------------------------------------------------
# 网络辅助函数
# ---------------------------------------------------------------------------

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

_FONT_EXT_RE = re.compile(r"\.(woff2?|ttf|otf|eot)(\?|$)", re.IGNORECASE)

# 需要镜像到本地、不能保留外链的 CDN 主机。
KEEP_CDN_HOSTS = {
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
}

def http_get(url: str, *, timeout: float = 60.0, headers: dict | None = None) -> bytes:
    """以 GET 请求 ``url`` 并返回正文；4xx/5xx 时抛出 HTTPError。"""
    h = dict(DEFAULT_HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    ctx = ssl.create_default_context()
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                raise
            last_err = e
        except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
            last_err = e
        # 依次退避 1 秒、2 秒。
        import time
        time.sleep(2 ** attempt)
    raise last_err if last_err else RuntimeError("fetch failed")

def http_get_optional(url: str, **kw) -> bytes | None:
    try:
        return http_get(url, **kw)
    except urllib.error.HTTPError as e:
        print(f"  skip {e.code} {url}")
        return None
    except Exception as e:
        print(f"  skip ERR {type(e).__name__}: {url}")
        return None

# ---------------------------------------------------------------------------
# URL 分类
# ---------------------------------------------------------------------------

def classify(url: str, page_url: str) -> tuple[str, str] | None:
    """决定 ``url`` 在磁盘中的保存位置。

    返回 ``(local_relpath, abs_url)``，跳过时返回 ``None``。站内资源保存为
    ``<foo>``，需镜像的 CDN 保存为 ``<host>/<path>``；其他绝对网络地址及
    ``mailto:``、``javascript:``、``data:``、锚点链接均跳过。
    """
    if not url or url.isspace():
        return None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme in ("mailto", "javascript", "data", "file"):
        return None
    if url.startswith("#"):
        return None
    page_parsed = urllib.parse.urlsplit(page_url)
    # 展开协议相对地址（"//host/path"）后重新分类。
    if parsed.scheme == "" and url.startswith("//"):
        abs_url = page_parsed.scheme + ":" + url
        return classify(abs_url, page_url)
    if parsed.scheme in ("http", "https"):
        if parsed.netloc in KEEP_CDN_HOSTS:
            # 保存到 <out_dir>/<host>/<path>，避免外站文件与根目录站内文件混杂。
            path = parsed.path.lstrip("/")
            return f"{parsed.netloc}/{path}", url
        # 同一主机只镜像看起来像媒体资源的地址。
        if parsed.netloc == page_parsed.netloc:
            return _same_host_asset(parsed, page_url)
        # 跳过其他主机。
        return None
    # 无协议地址属于文档相对或站点相对地址。
    abs_url = urllib.parse.urljoin(page_url, url)
    abs_parsed = urllib.parse.urlsplit(abs_url)
    if abs_parsed.scheme in ("http", "https") and abs_parsed.netloc == page_parsed.netloc:
        return _same_host_asset(abs_parsed, page_url)
    return None

# 同一主机只获取看起来像媒体的 URL，避免递归镜像无关页面。跳过 Hugo 永久链接
# 路由和所有以 "/" 结尾且没有扩展名的 URL。
_ASSET_EXT = (
    ".css", ".js", ".mjs", ".map", ".json", ".xml", ".webmanifest",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".mp4", ".webm", ".mov", ".m4v", ".ogg", ".mp3", ".wav", ".flac",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pdf", ".zip", ".tar", ".gz",
    ".txt", ".md",
)
_SKIP_PERMALINK_HINTS = (
    "/blog/", "/authors/", "/tags/", "/categories/", "/contact/", "/search/",
)

def _same_host_asset(parsed: urllib.parse.SplitResult, page_url: str) -> tuple[str, str] | None:
    path = parsed.path
    base = os.path.basename(path)
    # 类似 "/blog/" 的无扩展名目录是永久链接，应跳过。
    if path.endswith("/"):
        return None
    # 类似 "/blog" 的无扩展名路径也是永久链接，应跳过。
    if "." not in base:
        return None
    # 过滤 Hugo 风格永久链接的常见路径。
    for hint in _SKIP_PERMALINK_HINTS:
        if hint in path:
            return None
    rel = path.lstrip("/")
    if parsed.query:
        qs = re.sub(r"[^A-Za-z0-9._-]", "_", parsed.query)[:40]
        b, ext = os.path.splitext(rel)
        rel = f"{b}.{qs}{ext}"
    return rel, urllib.parse.urljoin(page_url, path + (("?" + parsed.query) if parsed.query else ""))

# ---------------------------------------------------------------------------
# HTML 资源提取
# ---------------------------------------------------------------------------

class _HTMLScanner(HTMLParser):
    # 不应视为资源 URL 的 <link rel> 值。
    NON_ASSET_LINK_REL = frozenset({
        "preconnect", "dns-prefetch", "canonical", "alternate",
    })
    # 明确指向资源的 <link rel> 值。
    ASSET_LINK_REL = frozenset({
        "stylesheet", "icon", "shortcut icon", "apple-touch-icon",
        "manifest", "preload", "modulepreload",
    })

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        rel_tokens = {t.strip().lower() for t in d.get("rel", "").split()}
        if tag == "link":
            # 跳过纯非资源 rel；混合 rel 和明确的资源 rel 仍保留。
            if rel_tokens and rel_tokens <= self.NON_ASSET_LINK_REL:
                return
            if rel_tokens and not (rel_tokens & self.ASSET_LINK_REL):
                # rel 含未知标记时保留 href，避免误删资源。
                pass
        for k in ("href", "src", "poster", "data-src"):
            v = d.get(k)
            if v:
                self.refs.append(v)
        srcset = d.get("srcset")
        if srcset:
            for piece in srcset.split(","):
                p = piece.strip().split()
                if p:
                    self.refs.append(p[0])
        style = d.get("style")
        if style:
            for u in re.findall(r"url\(([^)]+)\)", style):
                u = u.strip().strip("'\"").split()[0]
                self.refs.append(u)

def extract_html_refs(html: str) -> list[str]:
    s = _HTMLScanner()
    try:
        s.feed(html)
    except Exception:
        pass
    # 同时提取所有 <style> 块内的 url()。
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", html, re.IGNORECASE | re.DOTALL):
        for u in re.findall(r"url\(([^)]+)\)", m.group(1)):
            u = u.strip().strip("'\"").split()[0]
            s.refs.append(u)
    return s.refs

def extract_css_refs(css: str, css_url: str) -> list[str]:
    out = []
    for u in re.findall(r"url\(([^)]+)\)", css):
        u = u.strip().strip("'\"").split()[0]
        if u.startswith("data:"):
            continue
        out.append(urllib.parse.urljoin(css_url, u))
    return out

# ---------------------------------------------------------------------------
# 下载器
# ---------------------------------------------------------------------------

class Downloader:
    def __init__(self, out_dir: str, page_url: str):
        self.out_dir = os.path.abspath(out_dir)
        self.page_url = page_url
        self.fetched: set[str] = set()
        self.css_visited: set[str] = set()
        self.errors: list[tuple[str, str]] = []

    # 底层写入。

    def _write(self, rel: str, data: bytes) -> str:
        local = os.path.join(self.out_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, "wb") as f:
            f.write(data)
        return local

    # 单项资源。

    @staticmethod
    def _normalize_rel(rel: str) -> str:
        # cdn.jsdelivr.net 上的 KaTeX URL 带有 "/dist/"，改写后的 HTML 会去掉它；
        # 磁盘路径也去掉该段，保证二者一致。
        rel = rel.replace("@", "-")
        rel = re.sub(r"(cdn\.jsdelivr\.net/npm/katex-[0-9.]+)/dist/", r"\1/", rel)
        return rel

    def fetch_one(self, url: str) -> str | None:
        """下载 ``url``，返回本地相对路径；跳过时返回 ``None``。"""
        cls = classify(url, self.page_url)
        if not cls:
            return None
        rel, abs_url = cls
        rel = self._normalize_rel(rel)
        if rel in self.fetched:
            return rel
        if _FONT_EXT_RE.search(rel) is None and abs_url.lower().endswith((".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp4", ".webm", ".mov")):
            pass
        data = http_get_optional(abs_url)
        if data is None:
            return None
        local = self._write(rel, data)
        self.fetched.add(rel)
        print(f"  ok   {len(data):>10} {rel}")
        # 递归处理 CSS 中的 url()。
        if rel.endswith(".css"):
            self._walk_css(local, abs_url)
        return rel

    def _walk_css(self, css_local: str, css_url: str):
        if css_url in self.css_visited:
            return
        self.css_visited.add(css_url)
        try:
            with open(css_local, "rb") as f:
                css = f.read().decode("utf-8", errors="replace")
        except Exception:
            return
        for ref in extract_css_refs(css, css_url):
            try:
                self.fetch_one(ref)
            except Exception as e:
                self.errors.append((ref, str(e)))

    # 下载入口。

    def run(self, entry_html: str):
        # 发现入口 HTML 引用的资源。
        refs = extract_html_refs(entry_html)
        # 去重并保留原顺序。
        seen = set()
        ordered = []
        for r in refs:
            if r not in seen:
                seen.add(r)
                ordered.append(r)
        for r in ordered:
            try:
                self.fetch_one(r)
            except Exception as e:
                self.errors.append((r, str(e)))

# ---------------------------------------------------------------------------
# HTML 改写
# ---------------------------------------------------------------------------

def rewrite_html(html: str) -> str:
    # 移除 Cloudflare 邮箱保护脚本和链接。
    html = re.sub(
        r'<script[^>]*data-cfasync[^>]*src\s*=\s*"/cdn-cgi/scripts/[^"]*email-decode\.min\.js"[^>]*></script>',
        "",
        html,
    )
    # 从起始标签非贪婪匹配到对应的 </a>。
    html = re.sub(
        r'<a\b[^>]*?href\s*=\s*"/cdn-cgi/l/email-protection[^"]*"[^>]*>.*?</a>',
        '<a href="#" data-email="protected">[protected email]</a>',
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'href\s*=\s*"cdn-cgi/l/email-protection#[^"]*"',
        'href="#" data-email="protected"',
        html,
    )
    html = re.sub(
        r'href\s*=\s*"/cdn-cgi/l/email-protection#[^"]*"',
        'href="#" data-email="protected"',
        html,
    )

    # 移除 Cloudflare 分析信标。
    html = re.sub(
        r'<script[^>]*static\.cloudflareinsights\.com[^>]*></script>',
        "<!-- analytics removed for offline -->",
        html,
    )

    # 移除内联 Google Fonts 注入。
    html = re.sub(
        r'<script>\(function\(\)\{const e=document\.createElement\("link"\);e\.href="https://fonts\.googleapis\.com/css2\?[^"]+",[^<]+</script>',
        "<!-- Google Fonts removed for offline -->",
        html,
    )

    # 把 KaTeX CDN URL 改为不含 ``@`` 的本地路径，并与下载器的
    # <host>/<path> 保存结构保持一致。
    html = re.sub(
        r'https://cdn\.jsdelivr\.net/npm/katex@([0-9.]+)/dist/',
        r'cdn.jsdelivr.net/npm/katex-\1/',
        html,
    )
    html = re.sub(
        r'https://cdn\.jsdelivr\.net/npm/katex@([0-9.]+)/',
        r'cdn.jsdelivr.net/npm/katex-\1/',
        html,
    )

    # 把所有站点相对 "/foo" 引用改写为 "foo"。
    html = re.sub(
        r'(\b(?:href|src|poster|data-src)\s*=\s*["\'])/([^"\']*)["\']',
        lambda m: f'{m.group(1)}{m.group(2)}{m.group(0)[-1]}',
        html,
    )

    return html

def rewrite_css_paths(css: str) -> str:
    """把 CSS 中的 cdnjs.font-awesome URL 改写为 ../<relpath>。"""
    return css.replace(
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/",
        "../cdnjs.cloudflare.com/ajax/libs/font-awesome/",
    )

# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_fetch(args):
    page_url = args.url
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    print(f"Fetching {page_url}")
    html_bytes = http_get(page_url)
    html = html_bytes.decode("utf-8", errors="replace")

    dl = Downloader(out_dir, page_url)
    print("Discovering and downloading referenced resources...")
    dl.run(html)

    # 保存改写后的 index.html。
    rewritten = rewrite_html(html)
    with open(os.path.join(out_dir, "index.html"), "wb") as f:
        f.write(rewritten.encode("utf-8"))
    print(f"\nWrote {os.path.join(out_dir, 'index.html')} ({len(rewritten)} chars)")

    # index.html 写入后，再改写已下载 CSS 中完整的 FontAwesome HTTPS URL。
    for dirpath, _, files in os.walk(out_dir):
        for fn in files:
            if fn.endswith(".css"):
                p = os.path.join(dirpath, fn)
                with open(p, "rb") as f:
                    c = f.read().decode("utf-8", errors="replace")
                c2 = rewrite_css_paths(c)
                if c2 != c:
                    with open(p, "wb") as f:
                        f.write(c2.encode("utf-8"))

    # 验证结果。
    print("\nVerifying local relative URLs in index.html resolve to disk files...")
    # 同时处理有引号（"foo"）和无引号（foo）的属性值。
    attr_re = re.compile(
        r'(?:href|src|poster)\s*=\s*(?:"([^"]+)"|\'([^\']+)\'|([^\s>"\'`]+))',
        re.IGNORECASE,
    )
    local_urls = set()
    for m in attr_re.finditer(rewritten):
        v = m.group(1) or m.group(2) or m.group(3) or ""
        if v.startswith(("http://", "https://", "//", "#", "javascript:", "mailto:", "data:")):
            continue
        v = v.lstrip("/")
        if v:
            local_urls.add(v)
    missing = []
    for u in sorted(local_urls):
        if not os.path.exists(os.path.join(out_dir, u.replace("/", os.sep))):
            missing.append(u)
    if missing:
        print(f"  WARNING {len(missing)} missing local files:")
        for u in missing:
            print(f"    {u}")
    else:
        print(f"  OK  all {len(local_urls)} referenced local files present.")

    if dl.errors:
        print(f"\n{len(dl.errors)} resource(s) failed:")
        for url, err in dl.errors:
            print(f"  {url}: {err}")

    print("\nDone. To serve:  python download_website.py serve", out_dir)

class _SilentHandler:
    """为向后兼容保留的占位类。

    ``serve`` 子命令现在启动 ``python -m http.server``，不再于进程内运行自定义
    处理器。
    """

def cmd_serve(args):
    """以 site_dir 为根目录启动 ``python -m http.server``。

    这里直接使用标准库 HTTP 服务。包装器只负责传入正确的目录、绑定地址和端口，
    等待服务退出，并透传退出码。
    """
    site_dir = os.path.abspath(args.site_dir)
    port = args.port
    if not os.path.isdir(site_dir):
        sys.stderr.write(f"error: site directory not found: {site_dir}\n")
        return 2
    cmd = [
        sys.executable, "-u", "-m", "http.server",
        str(port),
        "--bind", "0.0.0.0",
        "--directory", site_dir,
    ]
    print(f"Serving {site_dir} at http://localhost:{port}/  (Ctrl-C to stop)")
    print(f"  -> {' '.join(cmd)}")
    try:
        rc = subprocess.call(cmd)
        return rc
    except KeyboardInterrupt:
        # http.server 会自行处理 SIGINT 并以 0 退出；这里只捕获 KeyboardInterrupt，
        # 避免父 shell 显示调用栈。
        return 0

# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="Download a page and its referenced assets")
    pf.add_argument("url")
    pf.add_argument("out_dir")
    pf.set_defaults(func=cmd_fetch)

    ps = sub.add_parser("serve", help="Serve a previously mirrored site")
    ps.add_argument("site_dir")
    ps.add_argument("--port", type=int, default=8000)
    ps.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    args.func(args)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
