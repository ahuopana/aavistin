# 29. Hazard causes and suggestion review in the risk register UI

Status: Accepted

## Context

After ADR 0028 a register could be filled and scored in the app, but a hazard's causes (and the controls that address them) were admin-only, and catalog suggestions could only be counted, not reviewed. `apps.risk.suggestions` already had `pending_suggestions`, `accept_suggestion` and `dismiss_suggestion`.

## Decisions

- **Causes on the hazard page**, one block per cause with its own controls: architecture links controls to "threats and hazard causes", and one hazard's causes (a thermal fuse failing vs. firmware tampering) are mitigated by different controls. Adding a cyberattack cause asks for the responsible threat of the same product, as `HazardCause.clean()` requires; other cause types never store a threat. Removing a cause keeps its controls.
- **The control forms are shared** with threats: linking, creating and unlinking take an optional `cause`; on a hazard it is required and must be one of that hazard's causes.
- **Catalog hints on an accepted hazard.** A catalog hazard listing a cyberattack cause can't get that cause on accept (it needs a threat), so the hazard page prompts for it until one exists. Its suggested controls are listed as a hint until a control of that name is linked to one of its causes.
- **A suggestions page per configuration**, linked from the register's "suggestions pending" count and its empty-state checklist. Only suggestions the configuration's current answers and findings trigger, and that are still undecided, can be accepted or dismissed; anything else is refused as "no longer pending".
- **Accepting a threat** can pick the asset it targets and, by default, add the catalog's suggested controls as planned controls, reusing a product control of the same name instead of creating a duplicate. Hazards are accepted as is (their auto-creatable causes are created as before).
- **Dismissing needs a reason.** Dismissed suggestions are listed with reason, who and when, and can be **accepted after all**, which flips the existing entry to accepted rather than creating a new one, keeping its history.

## Consequences

- Still admin-only: configuration deltas and risk assessment approval.
- Suggested controls are matched by exact name; renaming a control means the catalog hint for it reappears.
