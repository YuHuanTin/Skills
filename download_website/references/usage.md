# Usage notes

## fetch

```
python download_website.py fetch <URL> <out_dir>
```

Downloads the page at `<URL>` plus every reachable referenced asset to `<out_dir>`.
The script then writes a rewritten `index.html` into that directory and verifies
that every relative URL it references resolves to a file on disk.

Resources discovered:

- `<link href>` (CSS, icons, manifest)
- `<script src>`
- `<img src>`
- `<video src>` / `<video poster>` / `<source src>`
- `srcset=` attributes
- `url(...)` inside `<style>` blocks
- `url(...)` inside any downloaded CSS

Mirrored hosts (kept locally):

- Anything on the same host as the entry URL → `<out_dir>/<site-path>`
- `cdnjs.cloudflare.com` (FontAwesome, etc.)
- `cdn.jsdelivr.net` (KaTeX, etc.)

Other foreign hosts are skipped — the script never mirrors the open internet.

## serve

```
python download_website.py serve <site_dir> [--port 8000]
```

Spawns `python -m http.server <port> --bind 0.0.0.0 --directory <site_dir>`
and waits for it. Binding on `0.0.0.0` so other devices on the LAN can
connect. No custom HTTP handler — the user is running the standard library
server itself. Press Ctrl-C to stop.

If you prefer to run it directly:

```
python -m http.server 8000 --bind 0.0.0.0 --directory <site_dir>
```

## Troubleshooting

### KaTeX fonts 404

Older katex CSS pulled fonts from external URLs. Newer (0.16+) inlines all fonts
as base64, so no extra downloads are needed. If you do see font 404s, run
the script with `--verbose` and copy the missing font URLs into the
`KEEP_CDN_HOSTS` set in `classify()`.

### `@` in path 404

Python's `SimpleHTTPRequestHandler` treats `@` in the URL path as userinfo
(see RFC 3986). The script already replaces `@` with `-` in folder names for
this reason (`katex@0.16.28` → `katex-0.16.28`).

### JavaScript-only sites

The script mirrors the initial server response only. For SPAs (React, Vue,
Angular), launch a headless browser and save the rendered DOM instead.

### Cloudflare email-protection

The script removes Cloudflare's `/cdn-cgi/l/email-protection` mailto links
and the `email-decode.min.js` helper. The visible mailto link is replaced
with `[protected email]`. If the original email is needed, decode the
`/cdn-cgi/l/email-protection#...` URL on the original site.

## Re-running

The script does not de-duplicate against disk. Re-running it over an existing
directory is safe — files are overwritten — but no cached response is reused.
For idempotent runs, add an etag/last-modified cache keyed by URL.