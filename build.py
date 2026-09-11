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


def all_items(collection: str = COLLECTION) -> list[dict]:
    base = f"https://api.zotero.org/groups/{GROUP}/collections/{collection}/items/top"
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


def build(items: list[dict], links: dict[str, str], grants_by_id: dict[str, dict]) -> tuple[str, str]:
    by_year: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_year[year_of(it)].append(it)
    years = sorted(by_year, key=lambda y: (y != "Undated", y), reverse=True)
    parts: list[str] = []
    n = 0
    for y in years:
        parts.append(f"<h3>{html.escape(y)}</h3>\n<ul class=\"academy-pubs\">")
        for it in sorted(by_year[y], key=title_key):
            entry = strip_bib_wrapper(it.get("bib", ""))
            ft = links.get(it.get("key", ""))
            if ft:
                if ft not in entry:
                    entry += f' <a href="{html.escape(ft)}">{html.escape(ft)}</a>'
                if ft.startswith("https://doi.org/"):
                    entry += f' <a class="proxy" href="{html.escape(proxied(ft))}">[UA access]</a>'
            gl = grant_labels(it, grants_by_id)
            if gl:
                entry += f'<div class="grant">Output of: {html.escape("; ".join(gl))}.</div>'
            ab = abstract_of(it) if SITE_ABSTRACTS else ""
            if ab:
                entry += f'<div class="abstract">{html.escape(ab)}</div>'
            parts.append(f"  <li>{entry}</li>")
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
  .abstract {{ text-indent: 0; margin-top: .3rem; font-size: .92rem; color: #333; }}
  .grant {{ text-indent: 0; margin-top: .3rem; font-size: .85rem; color: #555; font-style: italic; }}
</style>
</head>
<body>
<h1>{html.escape(TITLE)}</h1>
{fragment}</body>
</html>
"""
    return page, fragment


SHOW_AMOUNTS = os.environ.get("SHOW_AMOUNTS", "1") == "1"
# Abstracts stay in Zotero. On the live site (2026-09-11) they rendered as unstyled full-size body text under
# every citation, 32 paragraph-long walls in one accordion, because Arizona Sites applies no CSS to .abstract.
# Off by default; SITE_ABSTRACTS=1 restores them for a standalone page that carries its own stylesheet.
SITE_ABSTRACTS = os.environ.get("SITE_ABSTRACTS", "0") == "1"


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
    # Only awarded money is shown or counted. A pending or submitted proposal may sit in the file for the record with
    # status: submitted; it is excluded from the lists and from the funding total until its status becomes awarded.
    return [g for g in data if g.get("show", True) and str(g.get("status", "awarded")).lower() == "awarded"]


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


PROXY_PREFIX = os.environ.get("PROXY_PREFIX", "https://ezproxy.library.arizona.edu/login?url=")
FULLTEXT_OVERRIDES = "fulltext.yml"


def proxied(url: str) -> str:
    return PROXY_PREFIX + url


def load_overrides() -> dict[str, str]:
    """Manual canonical-link overrides for records with no DOI and no usable URL (key = DOI or Zotero item key)."""
    if not os.path.exists(FULLTEXT_OVERRIDES):
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    with open(FULLTEXT_OVERRIDES, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(k).lower(): str(v) for k, v in data.items() if v}


def canonical_url(item: dict, overrides: dict[str, str]) -> str | None:
    """The publisher-of-record link: manual override, else the DOI, else the record's own URL. No third-party resolvers."""
    data = item.get("data", {})
    doi = (data.get("DOI") or "").strip()
    key = item.get("key", "")
    for k in (doi.lower(), key.lower()):
        if k and k in overrides:
            return overrides[k]
    if doi:
        return f"https://doi.org/{doi}"
    url = (data.get("url") or "").strip()
    return url or None


def grant_labels(item: dict, grants_by_id: dict[str, dict]) -> list[str]:
    """Items tagged `grant:<id>` in Zotero are marked as direct outputs of that grant (ids come from grants.yml)."""
    out = []
    for t in item.get("data", {}).get("tags", []):
        tag = str(t.get("tag", ""))
        if tag.lower().startswith("grant:"):
            gid = tag.split(":", 1)[1].strip().lower()
            g = grants_by_id.get(gid)
            out.append(g["title"] if g else gid)
    return out


def deliveries_of(item: dict) -> int:
    """A workshop or talk listed once but given several times carries a Zotero tag `delivered:<n>`; untagged counts as one.
    The list stays de-duplicated (one entry per title) while the numbers block counts every delivery (Ryan, 2026-09-11)."""
    for t in item.get("data", {}).get("tags", []):
        tag = str(t.get("tag", "")).lower()
        if tag.startswith("delivered:"):
            m = re.search(r"\d+", tag)
            if m:
                return max(1, int(m.group(0)))
    return 1


def abstract_of(item: dict) -> str:
    a = (item.get("data", {}).get("abstractNote") or "").strip()
    return re.sub(r"\s+", " ", a)


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


SECTIONS = [  # type-first, like the Eller AI Lab page; order is display order
    ("Journal Articles", {"journalArticle"}),
    ("Conference Papers", {"conferencePaper"}),
    ("Books, Chapters, and Reports", {"book", "bookSection", "report", "thesis", "computerProgram", "document", "manuscript"}),
]
SECTIONED = os.environ.get("SECTIONS_BY_TYPE", "1") == "1"


def award_labels(item: dict) -> list[str]:
    """Tags `award:<text>` render inline after the citation, e.g. award:Best Paper Award, ISCAP 2023."""
    return [str(t.get("tag", "")).split(":", 1)[1].strip() for t in item.get("data", {}).get("tags", []) if str(t.get("tag", "")).lower().startswith("award:")]


def md_entry(it: dict, n: int, links: dict[str, str], grants_by_id: dict[str, dict]) -> list[str]:
    line = html_to_md(strip_bib_wrapper(it.get("bib", "")))
    ft = links.get(it.get("key", ""))
    if ft:
        if ft not in line:
            line += f" [{ft}]({ft})"
        if ft.startswith("https://doi.org/"):   # the proxy twin only makes sense for publisher-of-record links
            line += f" [UA access]({proxied(ft)})"
    for a in award_labels(it):
        line += f" **{a}.**"
    out = [f"{n}. {line}"]
    gl = grant_labels(it, grants_by_id)
    ab = abstract_of(it) if SITE_ABSTRACTS else ""
    if gl or ab:
        out.append("")   # a blank line so the blockquote nests inside the list item rather than running on
    if gl:
        out.append(f"    *Output of: {'; '.join(gl)}.*")
        out.append("")
    if ab:
        out.append(f"    > {ab}")
        out.append("")
    return out


def md_years(items: list[dict], links: dict[str, str], grants_by_id: dict[str, dict], level: str) -> list[str]:
    by_year: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_year[year_of(it)].append(it)
    years = sorted(by_year, key=lambda y: (y != "Undated", y), reverse=True)
    out: list[str] = []
    for y in years:
        out.append(f"{level} {y}\n")
        for n, it in enumerate(sorted(by_year[y], key=title_key), 1):
            out.extend(md_entry(it, n, links, grants_by_id))
        out.append("")
    return out


def build_md(items: list[dict], links: dict[str, str], grants_by_id: dict[str, dict], sectioned: bool = SECTIONED) -> str:
    if not sectioned:
        return "\n".join(md_years(items, links, grants_by_id, "###")).rstrip() + "\n"
    out: list[str] = []
    placed: set[str] = set()
    for name, types in SECTIONS:
        group = [it for it in items if it.get("data", {}).get("itemType") in types]
        placed.update(it.get("key", "") for it in group)
        if not group:
            continue
        out.append(f"## {name}\n")
        out.extend(md_years(group, links, grants_by_id, "###"))
    rest = [it for it in items if it.get("key", "") not in placed]
    if rest:
        out.append("## Other\n")
        out.extend(md_years(rest, links, grants_by_id, "###"))
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
    overrides = load_overrides()
    links = {it.get("key", ""): u for it in items if (u := canonical_url(it, overrides))}
    grants = load_grants()
    grants_by_id = {str(g["id"]).lower(): g for g in grants if g.get("id")}
    page, fragment = build(items, links, grants_by_id)
    grants_fragment = build_grants(grants)
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    with open("docs/publications-fragment.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(fragment)
    with open("docs/grants-fragment.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(grants_fragment)
    with open("docs/publications.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(build_md(items, links, grants_by_id))
    with open("docs/grants.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(build_grants_md(grants))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if grants_fragment:
        with open("docs/grants.html", "w", encoding="utf-8", newline="\n") as f:
            f.write(page.split("<h1>")[0] + f"<h1>Arizona Cybersecurity Academy: Grants and Contracts</h1>\n" + grants_fragment + "</body>\n</html>\n")
    # Workshops and presentations: a second collection, same rendering, its own files.
    wcol = os.environ.get("ZOTERO_WORKSHOPS_COLLECTION", "MRCSGEM2")
    witems = all_items(wcol) if wcol else []
    # Talks given before the Academy existed are not Academy output. Ryan, 2026-09-11: nothing from 2022-2023
    # (a 2022 WiCyS talk was on the live page). Floor is a year; raise it if the Academy's start date moves.
    wmin = int(os.environ.get("WORKSHOPS_MIN_YEAR", "2024"))
    witems = [it for it in witems if year_of(it).isdigit() and int(year_of(it)) >= wmin]
    wlinks = {it.get("key", ""): u for it in witems if (u := canonical_url(it, overrides))}
    _, wfragment = build(witems, wlinks, grants_by_id)
    with open("docs/workshops.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(build_md(witems, wlinks, grants_by_id, sectioned=False) if witems else "")
    with open("docs/workshops-fragment.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(wfragment if witems else "")
    with open("docs/workshops.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(page.split("<h1>")[0] + f"<h1>Arizona Cybersecurity Academy: Workshops and Presentations</h1>\n" + wfragment + "</body>\n</html>\n")
    print(f"wrote {len(witems)} workshops and presentations")
    # "Research by the Numbers": the site cannot compute anything, so the block is generated here from the same
    # data as the lists and pasted the same way. Definitions (Ryan, 2026-09-11): funding = sum of shown grants;
    # peer-reviewed = journal articles + conference papers in Academy Output; presentations = the workshops list.
    peer = sum(1 for it in items if it.get("data", {}).get("itemType") in {"journalArticle", "conferencePaper"})
    funding = sum(float(g["amount"]) for g in grants if g.get("amount") is not None)
    deliveries = sum(deliveries_of(it) for it in witems)
    # Federal sponsors of the awarded grants, by short name, ordered by total dollars. Ryan, 2026-09-11: the third
    # hero slot is the sponsor line rather than a presentations count, which depends on tagging and decays.
    federal = {"National Science Foundation": "NSF", "National Security Agency": "NSA", "United States Department of Defense": "DoD", "National Institute of Standards and Technology": "NIST", "Department of Homeland Security": "DHS", "Department of Energy": "DOE", "National Institutes of Health": "NIH"}
    by_sponsor: dict[str, float] = defaultdict(float)
    for g in grants:
        short = federal.get(str(g.get("sponsor", "")).strip())
        if short:
            by_sponsor[short] += float(g.get("amount") or 0)
    sponsors = [s for s, _ in sorted(by_sponsor.items(), key=lambda kv: -kv[1])]
    stats = {"research_funding": funding, "peer_reviewed_publications": peer, "publications_total": len(items), "workshops_and_presentations": len(witems), "workshop_and_presentation_deliveries": deliveries, "grants": len(grants), "federal_sponsors": sponsors, "as_of": stamp}
    with open("docs/stats.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, indent=2)
        f.write("\n")
    numbers = (
        '<ul class="academy-numbers">\n'
        f'  <li><strong>${funding:,.0f}</strong><br>Research Funding</li>\n'
        f'  <li><strong>{peer}</strong><br>Peer-Reviewed Publications</li>\n'
        f'  <li><strong>{html.escape(", ".join(sponsors))}</strong><br>Federal Sponsors</li>\n'
        '</ul>\n'
    )
    with open("docs/numbers-fragment.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(numbers)
    print(f"numbers: ${funding:,.0f} funding, {peer} peer-reviewed of {len(items)} publications, {len(witems)} presentations, {deliveries} deliveries, federal sponsors {sponsors}")
    missing = [it["data"].get("title", "")[:70] for it in items if it.get("key", "") not in links]
    print(f"wrote {len(items)} publications ({len(links)} with a canonical link), {grants_fragment.count('<li>')} grants")
    for t in missing:
        print("  no canonical link (add to fulltext.yml or fix the Zotero record):", t)
    for it in items:
        if not abstract_of(it):
            print("  no abstract in Zotero:", it["data"].get("title", "")[:70])
    return 0


if __name__ == "__main__":
    sys.exit(main())
