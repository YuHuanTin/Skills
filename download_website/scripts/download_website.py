#!/usr/bin/env python3
"""
download_website.py — single-script offline website mirror.

Usage:
    python download_website.py fetch <URL> <out_dir>
        # download the page + every reachable referenced asset into out_dir

    python download_website.py serve <site_dir> [--port 8000]
        # spawn `python -m http.server` rooted at site_dir (bind 0.0.0.0)

What it does:
- Fetches the entry page HTML (browser User-Agent) using only stdlib (no curl/wget).
- Discovers resources by parsing href=, src=, poster=, srcset=, url(), and <video>/<source>.
- Categorises them:
    * site-relative paths (start with /)  -> under out_dir/<path>
    * cdn URLs that ship fonts/css/js      -> under out_dir/<cdn-host>/<path>
- Downloads each, retrying with exponential backoff on transient errors.
- Strips Cloudflare email-protection helpers, the analytics beacon, and any
  external Google Fonts link insertion from the saved HTML so the page no longer
  tries to reach the network.
- Rewrites every site-relative "/foo/bar" reference to "foo/bar" so it resolves
  from index.html when served as the root document.
- If KaTeX is referenced (katex.min.css / katex.min.js / auto-render.min.js),
  pulls them and any external font URLs the CSS references (KaTeX 0.16 inlines
  fonts as base64, so usually none are needed).  The folder is renamed
  katex-<version> (the literal "@" in katex@<ver> breaks Python's
  SimpleHTTPRequestHandler userinfo handling when the URL is percent-encoded).
- Rewrites the FontAwesome font URLs inside any downloaded stylesheet that
  points at cdnjs.cloudflare.com so they resolve locally.
- After fetching, prints a list of local relative URLs in the resulting HTML
  and verifies each one resolves to a file on disk.
- The "serve" sub-command simply spawns `python -m http.server` with the
  right --bind/--directory/port so the user is running the standard library
  HTTP server, not a custom handler.

Notes:
- Tested on Windows 10 with Python 3.14. Pure stdlib.
- Resolves HTML-relative URLs against the entry URL, not the page URL only,
  so links like "../images/foo.png" in a CSS file at /css/x.css land correctly.
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
# Network helpers
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

# CDN hosts we want to mirror locally instead of leaving external.
KEEP_CDN_HOSTS = {
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
}


def http_get(url: str, *, timeout: float = 60.0, headers: dict | None = None) -> bytes:
    """GET `url`, return body bytes. Raises urllib.error.HTTPError on 4xx/5xx."""
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
        # backoff: 1s, 2s
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
# URL classification
# ---------------------------------------------------------------------------

def classify(url: str, page_url: str) -> tuple[str, str] | None:
    """
    Decide where to put `url` on disk.

    Returns (local_relpath, abs_url) or None to skip.
    - Site-relative ("/foo") and same-host -> "<foo>"  (only for media-like URLs)
    - cdn host we mirror                   -> "<host>/<path>"
    - Other absolute http(s)               -> None (skip; we don't mirror the world)
    - mailto:/javascript:/data:/#         -> None
    """
    if not url or url.isspace():
        return None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme in ("mailto", "javascript", "data", "file"):
        return None
    if url.startswith("#"):
        return None
    page_parsed = urllib.parse.urlsplit(page_url)
    # Protocol-relative ("//host/path") -> expand and recurse
    if parsed.scheme == "" and url.startswith("//"):
        abs_url = page_parsed.scheme + ":" + url
        return classify(abs_url, page_url)
    if parsed.scheme in ("http", "https"):
        if parsed.netloc in KEEP_CDN_HOSTS:
            # Mirror at <out_dir>/<host>/<path> so foreign files don't mix with
            # site-relative files in the root.
            path = parsed.path.lstrip("/")
            return f"{parsed.netloc}/{path}", url
        # Same host? Mirror only if it looks like a media asset.
        if parsed.netloc == page_parsed.netloc:
            return _same_host_asset(parsed, page_url)
        # foreign host - skip
        return None
    # No scheme: doc-relative or site-relative
    abs_url = urllib.parse.urljoin(page_url, url)
    abs_parsed = urllib.parse.urlsplit(abs_url)
    if abs_parsed.scheme in ("http", "https") and abs_parsed.netloc == page_parsed.netloc:
        return _same_host_asset(abs_parsed, page_url)
    return None


# Only fetch same-host URLs that look like media (so we don't recursively
# mirror unrelated pages).  Hugo permalink routes we want to skip include
# /blog/, /authors/, /tags/, /categories/, /contact/, /, and any URL ending
# in "/" without a file extension.
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
    # "/blog/" -> no extension, ends with /  -> permalink, skip
    if path.endswith("/"):
        return None
    # "/blog" with no extension -> permalink, skip
    if "." not in base:
        return None
    # Hugo-style permalink hints
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
# HTML resource extraction
# ---------------------------------------------------------------------------

class _HTMLScanner(HTMLParser):
    # <link rel> values that should NOT be treated as asset URLs.
    NON_ASSET_LINK_REL = frozenset({
        "preconnect", "dns-prefetch", "canonical", "alternate",
    })
    # <link rel> values that explicitly point at an asset.
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
            # Skip pure non-asset rels (preconnect, dns-prefetch, canonical).
            # Mixed rels (e.g. "icon") and explicit asset rels are kept.
            if rel_tokens and rel_tokens <= self.NON_ASSET_LINK_REL:
                return
            if rel_tokens and not (rel_tokens & self.ASSET_LINK_REL):
                # rel contains tokens we don't recognise (e.g. author) - keep href just in case
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
    # also inline url() in any <style> blocks
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
# Downloader
# ---------------------------------------------------------------------------

class Downloader:
    def __init__(self, out_dir: str, page_url: str):
        self.out_dir = os.path.abspath(out_dir)
        self.page_url = page_url
        self.fetched: set[str] = set()
        self.css_visited: set[str] = set()
        self.errors: list[tuple[str, str]] = []

    # ----- low-level write --------------------------------------------------

    def _write(self, rel: str, data: bytes) -> str:
        local = os.path.join(self.out_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, "wb") as f:
            f.write(data)
        return local

    # ----- one resource -----------------------------------------------------

    @staticmethod
    def _normalize_rel(rel: str) -> str:
        # The katex assets on cdn.jsdelivr.net have a "/dist/" path segment
        # in the URL but our rewritten HTML drops it so the served URL is
        # shorter.  Strip "/dist/" from the katex folder so disk and HTML
        # line up.
        rel = rel.replace("@", "-")
        rel = re.sub(r"(cdn\.jsdelivr\.net/npm/katex-[0-9.]+)/dist/", r"\1/", rel)
        return rel

    def fetch_one(self, url: str) -> str | None:
        """Download `url`, return its local relpath or None if it was skipped."""
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
        # Recurse into CSS for url()
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

    # ----- entry ------------------------------------------------------------

    def run(self, entry_html: str):
        # Discover references in the entry HTML
        refs = extract_html_refs(entry_html)
        # De-dup, preserve order
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
# HTML rewriting
# ---------------------------------------------------------------------------

def rewrite_html(html: str) -> str:
    # Remove Cloudflare email-protection scripts and links
    html = re.sub(
        r'<script[^>]*data-cfasync[^>]*src\s*=\s*"/cdn-cgi/scripts/[^"]*email-decode\.min\.js"[^>]*></script>',
        "",
        html,
    )
    # Match the opening tag, then anything (non-greedy) up to the closing </a>.
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

    # Drop Cloudflare analytics beacon
    html = re.sub(
        r'<script[^>]*static\.cloudflareinsights\.com[^>]*></script>',
        "<!-- analytics removed for offline -->",
        html,
    )

    # Drop inline Google Fonts insertion
    html = re.sub(
        r'<script>\(function\(\)\{const e=document\.createElement\("link"\);e\.href="https://fonts\.googleapis\.com/css2\?[^"]+",[^<]+</script>',
        "<!-- Google Fonts removed for offline -->",
        html,
    )

    # Rewrite KaTeX CDN URLs to a local path that won't have '@'.
    # The downloader mirrors files at <host>/<path>, so we point the rewritten
    # HTML at the same relative path.
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

    # Rewrite every site-relative "/foo" reference to "foo"
    html = re.sub(
        r'(\b(?:href|src|poster|data-src)\s*=\s*["\'])/([^"\']*)["\']',
        lambda m: f'{m.group(1)}{m.group(2)}{m.group(0)[-1]}',
        html,
    )

    return html


def rewrite_css_paths(css: str) -> str:
    """Rewrite any cdnjs.font-awesome URL inside a CSS file to ../<relpath>."""
    return css.replace(
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/",
        "../cdnjs.cloudflare.com/ajax/libs/font-awesome/",
    )


# ---------------------------------------------------------------------------
# Sub-commands
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

    # Save rewritten index.html
    rewritten = rewrite_html(html)
    with open(os.path.join(out_dir, "index.html"), "wb") as f:
        f.write(rewritten.encode("utf-8"))
    print(f"\nWrote {os.path.join(out_dir, 'index.html')} ({len(rewritten)} chars)")

    # Now that index.html exists, also rewrite font-awesome URLs inside any CSS that
    # we downloaded with full https URLs.
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

    # Verify
    print("\nVerifying local relative URLs in index.html resolve to disk files...")
    # Handle both quoted ("foo") and unquoted (foo) attribute values.
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
    """Placeholder retained for backwards compatibility.  The `serve`
    sub-command now spawns `python -m http.server` instead of running
    a custom handler in-process."""


def cmd_serve(args):
    """Spawn `python -m http.server` rooted at site_dir.

    We don't reinvent the HTTP server here — http.server is part of the
    standard library and is what the user asked for.  This wrapper just
    spawns it with the right --directory / --bind / port, waits for it to
    exit, and propagates the exit code.
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
        # http.server handles SIGINT itself and exits with 0; we just need to
        # catch the KeyboardInterrupt so the parent shell doesn't see a
        # traceback.
        return 0


# ---------------------------------------------------------------------------
# CLI
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