#!/usr/bin/env python3
"""Scrape a Wix site (SSR HTML) into a GitHub Pages-friendly static folder.

This is NOT a perfect "Wix export" (Wix doesn't offer one). The goal is to:
- Download each page from the sitemap
- Save HTML as individual .html files
- Download referenced assets (css/js/images/fonts)
- Rewrite links in HTML/CSS so everything works when served from a static host

Usage:
  python3 tools/scrape_wix_static.py \
    --base-url https://www.yu-lab.org \
    --out-dir site

Notes:
- Many Wix sites embed a lot of runtime JS and load assets from Wix CDNs.
  We try to download and localize those assets where feasible.
- If some assets are generated dynamically after JS runs, you may need a
  headless-browser-based scrape. We'll try to keep this scraper robust.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Page:
    url: str
    out_html_path: Path


def _safe_filename_from_url(url: str) -> str:
    """Create a stable filename for an asset URL."""
    parsed = urllib.parse.urlparse(url)
    # keep extension if present
    base = posixpath.basename(parsed.path)
    if base and "." in base:
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    else:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        name = f"asset_{h}"
    if parsed.query:
        # avoid collisions across different querystrings
        qh = hashlib.sha256(parsed.query.encode("utf-8")).hexdigest()[:8]
        root, ext = os.path.splitext(name)
        name = f"{root}_{qh}{ext}"
    return name


def _is_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    return parsed.scheme in ("http", "https")


def _normalize_url(base_url: str, maybe_relative: str) -> str:
    return urllib.parse.urljoin(base_url, maybe_relative)


def _strip_fragment(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed._replace(fragment="").geturl()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _download_binary(session: requests.Session, url: str, out_path: Path) -> bool:
    """Download url to out_path if missing; returns True if downloaded/updated."""
    _ensure_parent(out_path)

    # If exists, keep it (we want determinism and speed)
    if out_path.exists() and out_path.stat().st_size > 0:
        return False

    r = session.get(url, timeout=45)
    r.raise_for_status()
    out_path.write_bytes(r.content)
    return True


CSS_URL_RE = re.compile(
    r"url\(\s*(?P<q>['\"]?)(?P<url>[^'\"\)]+)(?P=q)\s*\)", re.IGNORECASE
)


def _rewrite_css_and_download_assets(
    session: requests.Session,
    css_text: str,
    css_url: str,
    out_css_path: Path,
    assets_dir: Path,
    base_url: str,
    verbose: bool,
) -> str:
    """Rewrite CSS url(...) references to local assets and download them."""

    def repl(match: re.Match[str]) -> str:
        raw = match.group("url").strip()
        if raw.startswith("data:"):
            return match.group(0)

        raw = raw.replace("®istryLibrariesTopology", "registryLibrariesTopology")
        raw = raw.replace("falseregistryLibrariesTopology", "false&registryLibrariesTopology")
        raw = raw.replace("trueregistryLibrariesTopology", "true&registryLibrariesTopology")

        abs_url = _normalize_url(css_url, raw)
        abs_url = _strip_fragment(abs_url)

        # Only download assets for same-origin or known CDNs (Wix uses static.wixstatic.com etc.)
        # We'll allow any http(s) for now.
        if not _is_http_url(abs_url):
            return match.group(0)

        filename = _safe_filename_from_url(abs_url)
        local_path = assets_dir / filename
        try:
            _download_binary(session, abs_url, local_path)
        except Exception as e:
            if verbose:
                print(f"[css] failed to download {abs_url}: {e}")
            return match.group(0)

        # make path relative to css file
        rel = os.path.relpath(local_path, out_css_path.parent).replace(os.sep, "/")
        q = match.group("q") or ""
        return f"url({q}{rel}{q})"

    return CSS_URL_RE.sub(repl, css_text)


def _iter_sitemap_urls(session: requests.Session, sitemap_url: str) -> list[str]:
    r = session.get(sitemap_url, timeout=45)
    r.raise_for_status()
    xml = r.text

    # Wix can return a sitemapindex that points at pages-sitemap.xml
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    return [loc.strip() for loc in locs]


def _slug_to_html_filename(slug: str) -> str:
    """Map a URL path (/news) to an output HTML location.

    For GitHub Pages + Wix runtime compatibility we use "folder per route":
      /           -> index.html
      /news       -> news/index.html
      /a/b        -> a/b/index.html

    This lets the site be visited at clean URLs like /news/.
    """
    slug = slug.strip("/")
    if slug == "":
        return "index.html"
    return f"{slug}/index.html"


WORKER_FILENAME_RE = re.compile(r"clientWorker\.[^.]+\.bundle\.min\.js", re.I)


def _localize_wix_client_worker(
    *,
    session: requests.Session,
    soup: BeautifulSoup,
    out_html_path: Path,
    assets_dir: Path,
    verbose: bool,
) -> None:
    """Make the Wix Thunderbolt clientWorker same-origin.

    Wix bootstraps a WebWorker via `new Worker(workerUrl)`. Browsers require
    the worker script to be same-origin (unless you use a blob URL). Wix uses
    a remote URL (static.parastorage.com or /_partials/...), which breaks when
    hosting this HTML on GitHub Pages.

    The worker URL is embedded in the huge JSON blob `#wix-viewer-model`.
    We parse that JSON, download the worker JS, and rewrite the JSON to point
    at the local copy.
    """

    tag = soup.find("script", {"id": "wix-viewer-model"})
    if not tag or not tag.string:
        return

    try:
        model = json.loads(tag.string)
    except Exception as e:
        if verbose:
            print(f"[worker] failed to parse wix-viewer-model JSON: {e}")
        return

    changed = False

    def maybe_rewrite_value(v: str) -> str:
        nonlocal changed

        if not isinstance(v, str):
            return v
        if "clientWorker." not in v and "wix-thunderbolt" not in v:
            return v

        # Most important case
        if "clientWorker." not in v:
            return v

        # Wix may store this as a full URL (https://static.parastorage...) or as a
        # site-relative path (/ _partials/... ). We normalize to an absolute URL so
        # we can download it.
        raw = _strip_fragment(v)
        abs_url = raw
        if not _is_http_url(abs_url):
            if raw.startswith("/"):
                external_base = None
                try:
                    external_base = model.get("site", {}).get("externalBaseUrl")
                except Exception:
                    external_base = None
                if external_base:
                    abs_url = urllib.parse.urljoin(external_base.rstrip("/") + "/", raw.lstrip("/"))
                else:
                    return v
            else:
                return v

        filename = _safe_filename_from_url(abs_url)
        out_path = assets_dir / "wix-workers" / filename
        try:
            _download_binary(session, abs_url, out_path)
        except Exception as e:
            if verbose:
                print(f"[worker] failed to download {abs_url}: {e}")
            return v

        # IMPORTANT: Wix often loads the worker via a blob URL wrapper which then
        # calls importScripts(workerUrl). In a blob URL context, relative paths like
        # "../assets/..." are invalid. So we force an absolute, site-root URL.
        site_root = assets_dir.parent
        rel_from_site_root = out_path.relative_to(site_root).as_posix()
        changed = True
        return f"/{rel_from_site_root}"

    def walk(obj):
        nonlocal changed
        if isinstance(obj, dict):
            for k in list(obj.keys()):
                obj[k] = walk(obj[k])
            return obj
        if isinstance(obj, list):
            return [walk(x) for x in obj]
        if isinstance(obj, str):
            return maybe_rewrite_value(obj)
        return obj

    model = walk(model)

    if changed:
        tag.string.replace_with(json.dumps(model, separators=(",", ":"), ensure_ascii=False))


def _html_rewrite_and_download_assets(
    session: requests.Session,
    soup: BeautifulSoup,
    page_url: str,
    out_html_path: Path,
    assets_dir: Path,
    verbose: bool,
) -> None:
    """Download and localize assets referenced in HTML (link/script/img)."""

    def localize_attr(tag, attr: str) -> None:
        val = tag.get(attr)
        if not val:
            return
        if isinstance(val, list):
            return
        raw = val.strip()
        if raw.startswith("data:"):
            return
        if raw.startswith("mailto:") or raw.startswith("tel:"):
            return
        if raw.startswith("#"):
            return

        # BeautifulSoup decodes HTML entities in attributes. Wix URLs often contain
        # a query param named "registryLibrariesTopology" and HTML parsing can
        # turn the leading "&reg" into the registered-sign entity (®), producing
        # broken URLs like "®istryLibrariesTopology".
        raw = raw.replace("®istryLibrariesTopology", "registryLibrariesTopology")
        raw = raw.replace("falseregistryLibrariesTopology", "false&registryLibrariesTopology")
        raw = raw.replace("trueregistryLibrariesTopology", "true&registryLibrariesTopology")

        abs_url = _normalize_url(page_url, raw)
        abs_url = _strip_fragment(abs_url)
        if not _is_http_url(abs_url):
            return

        # Some Wix runtime bundles are requested via a very large querystring and
        # may return 400 when fetched outside the Wix runtime context.
        # For these, keep the remote URL so the page can still load them at runtime.
        if "siteassets.parastorage.com/pages/pages/thunderbolt" in abs_url:
            tag[attr] = abs_url
            return

        filename = _safe_filename_from_url(abs_url)
        local_path = assets_dir / filename
        try:
            _download_binary(session, abs_url, local_path)
        except Exception as e:
            if verbose:
                print(f"[html] failed to download {abs_url}: {e}")
            return

        rel = os.path.relpath(local_path, out_html_path.parent).replace(os.sep, "/")
        tag[attr] = rel

    # localize assets
    for link in soup.select("link[rel~='stylesheet'][href]"):
        href = link.get("href")
        if not href:
            continue
        css_url = _normalize_url(page_url, href)
        css_url = _strip_fragment(css_url)
        if not _is_http_url(css_url):
            continue

        filename = _safe_filename_from_url(css_url)
        out_css_path = assets_dir / filename

        try:
            r = session.get(css_url, timeout=45)
            r.raise_for_status()
            css_text = r.text
            css_text = _rewrite_css_and_download_assets(
                session=session,
                css_text=css_text,
                css_url=css_url,
                out_css_path=out_css_path,
                assets_dir=assets_dir,
                base_url=page_url,
                verbose=verbose,
            )
            _ensure_parent(out_css_path)
            out_css_path.write_text(css_text, encoding="utf-8")

            rel = os.path.relpath(out_css_path, out_html_path.parent).replace(os.sep, "/")
            link["href"] = rel
        except Exception as e:
            if verbose:
                print(f"[css] failed to download/rewrite stylesheet {css_url}: {e}")
            # Keep original href

    # scripts
    for script in soup.select("script[src]"):
        localize_attr(script, "src")

    # images
    for img in soup.select("img[src]"):
        localize_attr(img, "src")

    # source tags (video/audio)
    for source in soup.select("source[src]"):
        localize_attr(source, "src")

    # link icons
    for link in soup.select("link[href]"):
        rel = " ".join(link.get("rel") or [])
        if "stylesheet" in rel:
            continue
        localize_attr(link, "href")

    # NOTE: do NOT inject a <base> tag.
    # Wix's platform worker code uses `document.baseURI !== location.href` as a
    # signal to create a blob worker wrapper that calls `importScripts(url)`.
    # In a blob worker context, non-absolute URLs like "/assets/..." can be
    # considered invalid by `importScripts`, which breaks.
    #
    # Instead, we remove any <base> tags and rely on correct relative URLs.
    if soup.head:
        for base in list(soup.head.find_all("base")):
            base.decompose()

    # Localize Wix client worker (must happen after we finish rewriting local assets)
    _localize_wix_client_worker(
        session=session,
        soup=soup,
        out_html_path=out_html_path,
        assets_dir=assets_dir,
        verbose=verbose,
    )

    # rewrite internal anchors to local route folders
    page_parsed = urllib.parse.urlparse(page_url)
    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href or isinstance(href, list):
            continue
        h = href.strip()
        if h.startswith("#") or h.startswith("mailto:") or h.startswith("tel:"):
            continue

        abs_url = _normalize_url(page_url, h)
        parsed = urllib.parse.urlparse(abs_url)

        # only rewrite links pointing to this domain
        if parsed.netloc != page_parsed.netloc:
            continue

        # Keep query/fragment
        frag = f"#{parsed.fragment}" if parsed.fragment else ""
        query = f"?{parsed.query}" if parsed.query else ""

        # / -> /, /news -> /news/
        path = parsed.path or "/"
        if path == "/":
            a["href"] = f"/{query}{frag}".replace("/?", "?")
        else:
            a["href"] = f"{path.rstrip('/')}/{query}{frag}/".replace("//", "/")


def _get_page(session: requests.Session, url: str) -> str:
    # Wix sometimes varies based on user agent.
    r = session.get(url, timeout=45)
    r.raise_for_status()
    return r.text


def build_pages(base_url: str, urls: list[str], out_dir: Path) -> list[Page]:
    pages: list[Page] = []
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        out_name = _slug_to_html_filename(parsed.path or "/")
        pages.append(Page(url=url, out_html_path=out_dir / out_name))
    return pages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out-dir", default="site")
    ap.add_argument("--sitemap", default="/sitemap.xml")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    out_dir = Path(args.out_dir)

    # output structure
    assets_dir = out_dir / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA})

    sitemap_url = _normalize_url(base_url + "/", args.sitemap.lstrip("/"))

    # First sitemap might be a sitemapindex
    sitemap_locs = _iter_sitemap_urls(session, sitemap_url)
    if len(sitemap_locs) == 1 and sitemap_locs[0].endswith("pages-sitemap.xml"):
        sitemap_locs = _iter_sitemap_urls(session, sitemap_locs[0])

    # Filter to base domain pages only and remove sitemap urls
    page_urls = []
    for u in sitemap_locs:
        if u.endswith(".xml"):
            continue
        if u.startswith(base_url):
            page_urls.append(u)

    # Deduplicate
    page_urls = list(dict.fromkeys(page_urls))

    if args.verbose:
        print(f"Found {len(page_urls)} page URLs")
        for u in page_urls:
            print(" -", u)

    pages = build_pages(base_url, page_urls, out_dir)

    for page in pages:
        if args.verbose:
            print(f"Fetching {page.url}")
        html = _get_page(session, page.url)
        soup = BeautifulSoup(html, "html.parser")

        _html_rewrite_and_download_assets(
            session=session,
            soup=soup,
            page_url=page.url,
            out_html_path=page.out_html_path,
            assets_dir=assets_dir,
            verbose=args.verbose,
        )

        # ensure UTF-8
        _ensure_parent(page.out_html_path)
        page.out_html_path.write_text(str(soup), encoding="utf-8")

        # be polite
        time.sleep(0.5)

    # convenience: netlify/gh-pages style 404 (optional)
    if not (out_dir / "404.html").exists() and (out_dir / "index.html").exists():
        (out_dir / "404.html").write_text((out_dir / "index.html").read_text(encoding="utf-8"), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
