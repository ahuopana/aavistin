# Vendored front-end libraries

Served from our own origin so pages (and the end-to-end tests) do not
depend on a public CDN. No Node build is involved: files are the `dist`
builds published on npm, copied unmodified.

The name, version and licence of each file are in `manifest.json`, which
also feeds the User Guide's generated Licences page. Add every new file
there (a test checks this).

To upgrade: download the new `dist` file from npm, add it here under a
new versioned name, update `templates/base.html` and `manifest.json`, and
delete the old file. See `docs/development.md`.
