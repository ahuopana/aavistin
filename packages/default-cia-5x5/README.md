# default-cia-5x5

The default risk method: CIA-based asset/threat analysis with a 5x5
severity x likelihood matrix, matching the example in
`docs/architecture.md`, "Risk assessment: methods and catalogs". This is
a generic scoring framework we wrote, not derived from any standard.

## Importing

Run inside the `web` container (see the main `README.md`'s "Packages"
section for why), then review and approve in Django admin:

```bash
docker compose exec web python manage.py import_package packages/default-cia-5x5/1.0.0.json --kind method --official
docker compose exec web python manage.py approve_package default-cia-5x5 1.0.0
```
