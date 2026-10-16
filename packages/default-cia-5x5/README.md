# default-cia-5x5

The default risk method: CIA-based asset/threat analysis with a 5x5
severity x likelihood matrix, matching the example in
`docs/architecture.md`, "Risk assessment: methods and catalogs". This is
a generic scoring framework we wrote, not derived from any standard.

## Versions

- `1.0.0`: the first version; declares no impact categories, so the built-in defaults apply.
- `1.1.0`: declares its impact categories (ADR 0034): safety and property damage (which link to hazards), operational, financial, privacy, and legal and contractual.

## Importing

The easiest way is the admin's **Import package** page (see "Installing
requirement packages" in the main `README.md`). From the command line, run
inside the `web` container, then review and approve in Django admin:

```bash
docker compose exec web python manage.py import_package packages/default-cia-5x5/1.1.0.json --kind method --official
docker compose exec web python manage.py approve_package default-cia-5x5 1.1.0
```

Approving 1.1.0 supersedes 1.0.0. Existing consequences keep their category ids, which both versions share.
