#!/usr/bin/env python3
"""Strip Wix/Thunderbolt runtime scripts from exported HTML.

This repo contains HTML exported from Wix that is already SSR-rendered.
However, the HTML still bootstraps Wix Thunderbolt runtime and makes
cross-origin requests (including a cross-origin web worker). That breaks
when hosting on GitHub Pages as a standalone static site.

This script keeps the already-rendered DOM and local assets, but removes
Wix runtime scripts/preloads that phone home to parastorage/wixstatic.

Heuristics:
- Remove <script> tags that have a remote src (http/https//) or a data-url
  pointing to static.parastorage.com (Thunderbolt bundles).
- Remove <link rel="preload"> / <link rel="prefetch"> that point remote.
- Remove <script type="application/json"> viewer model blocks (wix viewerModel)
  which are used by the runtime.
- Remove other known Wix-specific bootstrap scripts by id prefix "wix-".

This produces a static snapshot that should render without errors.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup
from bs4 import Comment

REMOTE_RE = re.compile(r"^(https?:)?//", re.I)
WIX_HOST_RE = re.compile(r"(wixstatic\.com|parastorage\.com|wix\.com)", re.I)


def is_remote_url(url: str | None) -> bool:
    if not url:
        return False
    return bool(REMOTE_RE.match(url))


def is_wix_remote(url: str | None) -> bool:
    if not url:
        return False
    return bool(WIX_HOST_RE.search(url))


def strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    removed = 0

    # Remove <base href="/"> which can break subpath hosting and local nav
    base = soup.find("base")
    if base:
        base.decompose()
        removed += 1

    # Remove scripts.
    #
    # For a true static snapshot, we keep only structured data scripts.
    # Everything else (even local thunderbolt bundles) is removed.
    for script in list(soup.find_all("script")):
        script_type = (script.get("type") or "").lower()

        # Keep structured data
        if script_type == "application/ld+json":
            continue

        # Drop everything else (runtime, analytics, embeds placeholders, etc.)
        script.decompose()
        removed += 1

    # Remove remote/preload links.
    for link in list(soup.find_all("link")):
        rel = (link.get("rel") or [])
        href = link.get("href")
        as_attr = link.get("as")

        rel_set = {r.lower() for r in rel}

        if is_remote_url(href) or is_wix_remote(href):
            # Keep the favicon if it is local; otherwise remove.
            link.decompose()
            removed += 1
            continue

        # Strip speculationrules, preloads, etc. Not needed for static.
        if "preload" in rel_set or "prefetch" in rel_set or "modulepreload" in rel_set:
            link.decompose()
            removed += 1
            continue

        # Some Wix stylesheets come in as <style data-href="https://..."> not <link>
        # so nothing to do here.

    # Remove <style> blocks that directly include remote @import or urls.
    for style in list(soup.find_all("style")):
        data_url = style.get("data-url")
        data_href = style.get("data-href")
        if is_remote_url(data_url) or is_wix_remote(data_url) or is_remote_url(data_href) or is_wix_remote(data_href):
            style.decompose()
            removed += 1
            continue

        txt = style.string or ""
        if WIX_HOST_RE.search(txt) and "@font-face" not in txt:
            # keep font-face blocks; remove other wix runtime css
            style.decompose()
            removed += 1
            continue

    # Remove custom elements that rely on Wix runtime (best-effort)
    for tag_name in ["wix-dropdown-menu", "wix-video", "wix-bg-image", "wix-iframe"]:
        for el in list(soup.find_all(tag_name)):
            # Replace with its inner HTML so content remains.
            el.unwrap()

    # Ensure html lang exists
    if soup.html and not soup.html.get("lang"):
        soup.html["lang"] = "en"

    # Add a comment marker
    if soup.head:
        soup.head.append(Comment(" Stripped Wix runtime for static hosting "))

    # Return pretty-ish HTML (avoid full prettify that can break inline svg)
    return str(soup)


def process_file(path: Path, in_place: bool) -> tuple[Path, bool]:
    original = path.read_text(encoding="utf-8", errors="ignore")
    stripped = strip_html(original)
    changed = stripped != original

    if in_place and changed:
        path.write_text(stripped, encoding="utf-8")

    return path, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="site", help="Root directory to process")
    parser.add_argument("--in-place", action="store_true", help="Modify files in place")
    args = parser.parse_args()

    root = Path(args.root)
    html_files = sorted(root.rglob("*.html"))

    any_changed = False
    for f in html_files:
        # Don't touch Decap CMS admin UI
        if "admin" in f.parts:
            continue

        _, changed = process_file(f, args.in_place)
        if changed:
            any_changed = True

    if not any_changed:
        print("No changes made.")
    else:
        print(f"Processed {len(html_files)} HTML files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
