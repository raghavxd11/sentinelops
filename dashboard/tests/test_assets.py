"""The dashboard must work offline: no CDN or Google Fonts requests.

These tests fail if a template or stylesheet loads anything from an external
URL, or if a page references a static file that is not in the repo.
"""
import re
from pathlib import Path

import seed

APP_DIR = Path(__file__).resolve().parent.parent / "app"
TEMPLATES = sorted((APP_DIR / "templates").rglob("*.html"))
STYLESHEETS = sorted((APP_DIR / "static").rglob("*.css"))

# A tag that makes the browser fetch something, pointing at http://, https:// or //host.
# Plain <a href="https://..."> links are fine: the browser only follows them on click.
EXTERNAL_TAG = re.compile(
    r"""<(?:link|script|img|source|iframe|video|audio|embed|object)\b[^>]*?
        \b(?:href|src|data)\s*=\s*["']\s*(?:https?:)?//""",
    re.IGNORECASE | re.VERBOSE,
)
# url(https://...) or @import "https://..." inside CSS (data: URIs are local, so allowed).
EXTERNAL_CSS = re.compile(
    r"""url\(\s*["']?\s*(?:https?:)?//|@import\s+["']\s*(?:https?:)?//""",
    re.IGNORECASE,
)
# src="/static/..." or href="/static/..." in rendered HTML.
STATIC_URL = re.compile(r"""(?:src|href)="(/static/[^"?#]+)""")
# url("file.woff2") in CSS, ignoring data: URIs and #fragment references.
CSS_URL = re.compile(r"""url\(\s*["']?(?!data:|#)([^"')?#]+)""")


def test_templates_and_stylesheets_were_found():
    assert len(TEMPLATES) >= 10
    assert any(path.name == "app.css" for path in STYLESHEETS)


def test_no_template_loads_an_external_asset():
    offenders = [
        f"{path.relative_to(APP_DIR)}: {match.group(0)}"
        for path in TEMPLATES
        for match in EXTERNAL_TAG.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_no_template_has_inline_external_css():
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in TEMPLATES
        if EXTERNAL_CSS.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_no_stylesheet_loads_an_external_file():
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in STYLESHEETS
        if EXTERNAL_CSS.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_check_itself_catches_cdn_links():
    """Guards the regexes above, so the tests cannot pass by matching nothing."""
    assert EXTERNAL_TAG.search('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>')
    assert EXTERNAL_TAG.search('<link rel="stylesheet" href="//fonts.googleapis.com/css2">')
    assert EXTERNAL_CSS.search("src: url(https://fonts.gstatic.com/plex.woff2)")
    assert not EXTERNAL_TAG.search('<a class="link" href="https://github.com/x/y">repo</a>')
    assert not EXTERNAL_CSS.search('background: url("data:image/svg+xml,<svg xmlns=...>")')


def test_every_static_file_a_page_references_is_served(client, auth_client):
    seed.seed()  # so the Overview page includes the chart scripts
    pages = [client.get("/login"), auth_client.get("/overview"), auth_client.get("/services")]

    referenced = set()
    for page in pages:
        referenced.update(STATIC_URL.findall(page.get_data(as_text=True)))

    assert any("chart" in url for url in referenced)
    assert any("bootstrap.min.css" in url for url in referenced)
    for url in sorted(referenced):
        assert client.get(url).status_code == 200, url


def test_every_file_a_stylesheet_references_exists():
    missing = []
    for path in STYLESHEETS:
        for target in CSS_URL.findall(path.read_text(encoding="utf-8")):
            if not (path.parent / target.strip()).is_file():
                missing.append(f"{path.relative_to(APP_DIR)} -> {target}")
    assert missing == []
