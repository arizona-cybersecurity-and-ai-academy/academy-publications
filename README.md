# Academy publications page

Generates the research lists for the Arizona Cybersecurity Academy website from the Academy's Zotero group library (group 6382800). Three collections feed three lists:

| List | Zotero collection | Output files |
|---|---|---|
| Publications | Academy Output | `docs/publications.md`, `docs/publications-fragment.html`, `docs/index.html` |
| Workshops and presentations | Workshops and Presentations | `docs/workshops.md`, `docs/workshops-fragment.html`, `docs/workshops.html` |
| Grants and contracts | `grants.yml` in this repository (not Zotero) | `docs/grants.md`, `docs/grants-fragment.html`, `docs/grants.html` |

Zotero renders each entry in APA; the publications list is sectioned by type (journal articles, conference papers, then books, chapters and reports), with years newest first inside each section and a numbered list per year, after the Eller AI Lab page. A record tagged `award:<text>` prints that award in bold after its citation. Each entry carries its canonical link (DOI or publisher URL) and, for DOI links, a University of Arizona library twin through `ezproxy.library.arizona.edu`. Abstracts come from the Zotero record. A record tagged `grant:<id>`, where the id is one declared in `grants.yml`, gets an "Output of" line naming the grant. No third-party resolvers are used anywhere in the build.

The GitHub Action runs every Monday morning and on demand, and commits only when a list changed, so the commit history is the change log.

## Adding to the lists

- **A publication or a workshop:** add the record to the matching collection in the Zotero group, ideally from the publisher's page with Zotero's browser connector so the metadata arrives clean, and attach the PDF. The next build picks it up.
- **Workshops and presentations before 2024 are dropped** at build time (`WORKSHOPS_MIN_YEAR`, default 2024): talks given before the Academy existed are not Academy output, whatever the Zotero collection holds.
- **A grant:** add an entry to `grants.yml`. `show: false` keeps an entry on record without publishing it; `id` is an optional slug that lets Zotero records be tagged as outputs of that grant.
- **A record with no DOI and no usable URL:** add its publisher-of-record URL to `fulltext.yml`, keyed by DOI or Zotero item key.

## Setup

1. Add a repository secret `ZOTERO_API_KEY` holding a Zotero API key with read access to the group. A key scoped to the group, read-only, is enough. The group is private, so the build cannot run without it.
2. Run the workflow once from the Actions tab to produce the first lists.

## Local run

```bash
ZOTERO_API_KEY=... python build.py
```

## Updating the website

Arizona Sites (Quickstart) cannot load modules. Its editor takes the generated HTML fragments as-is (verified on the live Research page, 2026-09-11: classes, links and the UA-proxy twins all survived), so paste `docs/publications-fragment.html`, `docs/workshops-fragment.html` and `docs/grants-fragment.html`. Do not paste the full pages (`index.html`, `workshops.html`, `grants.html`): they carry an `<h1>` and a "Generated ..." line meant for a standalone page, and both showed up inside the site's accordions. The Markdown files are the fallback if the editor is switched to a Markdown-only format. Replace the whole block each time rather than editing entries in place; the site applies its own theme.

Abstracts are not in the site output. The site applies no styling to them, so they rendered as full-size body text under every citation. They stay in Zotero; `SITE_ABSTRACTS=1` restores them for a standalone page that carries its own stylesheet.

To be told when a list changes without a GitHub account, follow the commit feed at `https://github.com/arizona-cybersecurity-and-ai-academy/academy-publications/commits/master.atom` (Outlook reads RSS natively). With a GitHub account, watching the repository sends an email per update.
