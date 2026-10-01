# Vendored front-end libraries

Served from our own origin so pages (and the end-to-end tests) do not
depend on a public CDN. Both are MIT licensed. No Node build is involved:
files are the `dist` builds published on npm, copied unmodified.

| File | Library | Version | Source |
| --- | --- | --- | --- |
| `alpine-3.17.4.min.js` | Alpine.js | 3.17.4 | `alpinejs/dist/cdn.min.js` |
| `htmx-2.0.4.min.js` | htmx | 2.0.4 | `htmx.org/dist/htmx.min.js` |

To upgrade: download the new `dist` file from npm, replace it here under a
new versioned name, and update `templates/base.html`.
