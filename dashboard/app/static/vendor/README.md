# Vendored front-end assets

Third-party files are kept in the repo so the dashboard makes no CDN or Google
Fonts requests and works offline (for example on an EC2 instance with no
outbound access, or during a demo without internet).

| Folder             | Package                    | Version | License | Downloaded from |
|--------------------|----------------------------|---------|---------|-----------------|
| `bootstrap/`       | Bootstrap (CSS + JS bundle) | 5.3.3   | MIT     | `cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/` |
| `bootstrap-icons/` | Bootstrap Icons (CSS + fonts) | 1.11.3 | MIT    | `cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/` |
| `chartjs/`         | Chart.js (UMD build)       | 4.4.7   | MIT     | `cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.js` |
| `ibm-plex/`        | IBM Plex Sans, IBM Plex Mono (woff2, latin, 400/500/600) | Fontsource 5.3.0 | SIL OFL 1.1 | `cdn.jsdelivr.net/npm/@fontsource/ibm-plex-sans/files/`, `.../ibm-plex-mono/files/` |

Changes made to the downloaded files:

- The trailing `sourceMappingURL` comment was removed from `bootstrap.min.css`,
  `bootstrap.bundle.min.js` and `chart.umd.js`, because the `.map` files are not
  vendored and the browser would request them when DevTools is open.
- `ibm-plex/fonts.css` is written by hand: six `@font-face` rules pointing at the
  woff2 files in the same folder.

Nothing else is modified. To upgrade a package, replace its files with the new
version and update this table. `tests/test_assets.py` fails if a template or
stylesheet references an external URL, or if a referenced static file is missing.
