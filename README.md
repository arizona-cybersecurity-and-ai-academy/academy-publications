# Academy publications page

Generates the Publications page for the Arizona Cybersecurity Academy website from the Academy's Zotero group library (group 6382800, collection "Academy Output"). Zotero renders each entry in APA; the script groups them by year and writes `docs/index.html` (a complete page) and `docs/publications-fragment.html` (the bare list for pasting into the Arizona Sites editor).

The GitHub Action runs every Monday morning and on demand, and commits only when the list changed, so the commit history is the change log.

## Setup

1. Add a repository secret `ZOTERO_API_KEY` with a Zotero API key that has read access to the group (a key scoped to the group, read-only, is enough). The group is private, so the build cannot run without it.
2. Run the workflow once from the Actions tab to produce the first list.

## Local run

```bash
ZOTERO_API_KEY=... python build.py
```

## Updating the site

Arizona Sites (Quickstart) cannot load modules, so the page is maintained by hand from this output. The editor accepts Markdown and nothing more technical (Veronika Kyles, 2026-09-10), so the files to paste are `docs/publications.md` and `docs/grants.md`; the site applies its own theme. The HTML outputs are kept for any future embed option.
