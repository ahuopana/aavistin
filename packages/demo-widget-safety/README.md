# demo-widget-safety

A fictional package used only by the automated tests for the import
pipeline (`apps/packages`). "Widgets" are not a real product category and
this package is not derived from, or a summary of, any real regulation
or standard (EU CRA, RED, LVD, GDPR, EN/IEC/ISO or otherwise) — it was
written from scratch for testing.

`1.0.0.json` and `1.1.0.json` exist to exercise the diff-against-previous
and supersedes flow (`1.1.0` supersedes `1.0.0`, adds a question, and
tightens the high-power classification threshold).
