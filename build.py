"""Build the Arizona Cybersecurity Academy publications page from the Zotero group.

Reads the "Academy Output" collection of the Academy group library through the Zotero Web API,
lets Zotero render each entry in APA, groups entries by year (newest first), and writes two files:

  docs/index.html                 a complete standalone page (for GitHub Pages or an embed)
  docs/publications-fragment.html the bare list, for pasting into the Arizona Sites editor

Only the rendered output is committed; the workflow commits only when it changed.
Configuration is by environment variable so nothing library-specific is hard-coded in the workflow.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

GROUP = os.environ.get("ZOTERO_GROUP", "6382800")
COLLECTION = os.environ.get("ZOTERO_COLLECTION", "GAIH6QIZ")
STYLE = os.environ.get("CSL_STYLE", "apa")
API_KEY = os.environ.get("ZOTERO_API_KEY", "")
TITLE = os.environ.get("PAGE_TITLE", "Arizona Cybersecurity Academy: Publications")
UA = "academy-publications-build/1.0 (mailto:ryanstraight@arizona.edu)"


def fetch(url: str) -> tuple[list, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Zotero-API-Version": "3", **({"Zotero-API-Key": API_KEY} if API_KEY else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), dict(r.headers)


def all_items() -> list[dict]:
    base = f"https://api.zotero.org/groups/{GROUP}/collections/{COLLECTION}/items/top"
    q = {"format": "json", "include": "data,bib", "style": STYLE, "linkwrap": "1", "limit": "100", "start": "0"}
    out: list[dict] = []
    while True:
        items, headers = fetch(base + "?" + urllib.parse.urlencode(q))
        out.extend(items)
        if len(items) < 100:
            break
        q["start"] = str(int(q["start"]) + 100)
    return out


def year_of(item: dict) -> str:
    d = item.get("meta", {}).get("parsedDate") or item.get("data", {}).get("date") or ""
    m = re.search(r"\d{4}", d)
    return m.group(0) if m else "Undated"


def title_key(item: dict) -> str:
    return (item.get("data", {}).get("title") or "").lower()


def strip_bib_wrapper(bib: str) -> str:
    # Zotero returns <div class="csl-bib-body"><div class="csl-entry">...</div></div>; keep the entry only.
    m = re.search(r'<div class="csl-entry">(.*)</div>\s*</div>\s*$', bib, re.S)
    return m.group(1).strip() if m else bib.strip()


def build(items: list[dict]) -> tuple[str, str]:
    by_year: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_year[year_of(it)].append(it)
    years = sorted(by_year, key=lambda y: (y != "Undated", y), reverse=True)
    parts: list[str] = []
    n = 0
    for y in years:
        parts.append(f"<h3>{html.escape(y)}</h3>\n<ul class=\"academy-pubs\">")
        for it in sorted(by_year[y], key=title_key):
            parts.append(f"  <li>{strip_bib_wrapper(it.get('bib', ''))}</li>")
            n += 1
        parts.append("</ul>")
    fragment = "\n".join(parts) + "\n"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(TITLE)}</title>
<style>
  body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #1e1e1e; background: #fff; }}
  h1 {{ font-size: 1.6rem; }}
  h3 {{ margin-top: 1.75rem; border-bottom: 1px solid #ddd; padding-bottom: .25rem; }}
  ul.academy-pubs {{ list-style: none; padding-left: 0; }}
  ul.academy-pubs li {{ margin: 0 0 .9rem 0; padding-left: 2rem; text-indent: -2rem; }}
  a {{ color: #0c234b; }}
  .meta {{ color: #555; font-size: .85rem; }}
</style>
</head>
<body>
<h1>{html.escape(TITLE)}</h1>
<p class="meta">{n} publications. Generated {stamp} from the Academy Zotero library.</p>
{fragment}</body>
</html>
"""
    return page, fragment


SHOW_AMOUNTS = os.environ.get("SHOW_AMOUNTS", "1") == "1"


def load_grants(path: str = "grants.yml") -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        import yaml  # type: ignore
    except ImportError:
        print("pyyaml not installed; skipping grants", file=sys.stderr)
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    return [g for g in data if g.get("show", True)]


def build_grants(grants: list[dict]) -> str:
    if not grants:
        return ""
    def start_year(g: dict) -> int:
        m = re.search(r"\d{4}", str(g.get("years", "")))
        return int(m.group(0)) if m else 0
    rows: list[str] = []
    for g in sorted(grants, key=lambda g: (-start_year(g), str(g.get("title", "")).lower())):
        sponsor = g.get("sponsor", "")
        if g.get("prime"):
            sponsor += f" (via {g['prime']})"
        bits = [f"<strong>{html.escape(str(g.get('title', '')))}</strong>", html.escape(sponsor), html.escape(str(g.get("years", "")))]
        if SHOW_AMOUNTS and g.get("amount") is not None:
            bits.append(f"${float(g['amount']):,.0f}")
        if g.get("role"):
            bits.append(html.escape(str(g["role"])))
        line = ". ".join(b for b in bits if b)
        if g.get("note"):
            line += f" <span class=\"note\">{html.escape(str(g['note']))}</span>"
        rows.append(f"  <li>{line}.</li>")
    return "<ul class=\"academy-grants\">\n" + "\n".join(rows) + "\n</ul>\n"


def html_to_md(s: str) -> str:
    """Convert Zotero's CSL HTML for one entry into Markdown the Arizona Sites editor accepts."""
    s = re.sub(r"</?div[^>]*>", "", s)
    s = re.sub(r"<i>(.*?)</i>", r"*\1*", s, flags=re.S)
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s, flags=re.S)
    s = re.sub(r'<a href="([^"]+)">(.*?)</a>', lambda m: f"[{html.unescape(m.group(2))}]({m.group(1)})", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_md(items: list[dict]) -> str:
    by_year: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_year[year_of(it)].append(it)
    years = sorted(by_year, key=lambda y: (y != "Undated", y), reverse=True)
    out: list[str] = []
    for y in years:
        out.append(f"### {y}\n")
        for it in sorted(by_year[y], key=title_key):
            out.append(f"- {html_to_md(strip_bib_wrapper(it.get('bib', '')))}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def build_grants_md(grants: list[dict]) -> str:
    if not grants:
        return ""
    def start_year(g: dict) -> int:
        m = re.search(r"\d{4}", str(g.get("years", "")))
        return int(m.group(0)) if m else 0
    out: list[str] = []
    for g in sorted(grants, key=lambda g: (-start_year(g), str(g.get("title", "")).lower())):
        sponsor = g.get("sponsor", "")
        if g.get("prime"):
            sponsor += f" (via {g['prime']})"
        bits = [f"**{g.get('title', '')}**", sponsor, str(g.get("years", ""))]
        if SHOW_AMOUNTS and g.get("amount") is not None:
            bits.append(f"${float(g['amount']):,.0f}")
        if g.get("role"):
            bits.append(str(g["role"]))
        line = ". ".join(b for b in bits if b) + "."
        if g.get("note"):
            line += f" {g['note']}"
        out.append(f"- {line}")
    return "\n".join(out) + "\n"


def main() -> int:
    items = all_items()
    if not items:
        print("no items in collection; writing an empty list", file=sys.stderr)
    page, fragment = build(items)
    grants_fragment = build_grants(load_grants())
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    with open("docs/publications-fragment.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(fragment)
    with open("docs/grants-fragment.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(grants_fragment)
    with open("docs/publications.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(build_md(items))
    with open("docs/grants.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(build_grants_md(load_grants()))
    if grants_fragment:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open("docs/grants.html", "w", encoding="utf-8", newline="\n") as f:
            f.write(page.split("<h1>")[0] + f"<h1>Arizona Cybersecurity Academy: Grants and Contracts</h1>\n<p class=\"meta\">Awarded grants and contracts. Generated {stamp}.</p>\n" + grants_fragment + "</body>\n</html>\n")
    print(f"wrote {len(items)} publications, {grants_fragment.count('<li>')} grants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
