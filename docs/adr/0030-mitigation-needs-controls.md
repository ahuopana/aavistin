# 30. A mitigation needs controls, and counts once they are in place

Status: Accepted

## Context

With ADR 0028 a treatment of type *mitigate* with an acceptable residual rating needed neither a justification nor a control, so "mitigated, residual low" could be recorded with nothing behind it, and the product and portfolio risk bars counted it as acceptable.

## Decisions

- **A mitigation needs at least one control.** Saving a *mitigate* treatment requires a control linked to the threat, or to one of the hazard's causes. The control (name, description, status) is the plan for how the risk is reduced; no separate plan field is added.
- **Its residual rating counts only once the controls are in place.** `apps.risk.mitigation.mitigation_state` gives *no controls*, *mitigation planned* (any linked control still `planned`) or *controls in place* (all `implemented` or `verified`). `risk_ratio` (product page, welcome dashboard, Compliance Overview) counts an entry as acceptable only if every treatment's residual is acceptable **and** each mitigation is in place. Accept, transfer and avoid are decisions, not plans, and keep counting as before (they already need a justification).
- **Unlinking afterwards is allowed** (a control may be replaced), but the treatment then shows *no controls linked* and stops counting until a control is linked again or the treatment changes.
- **Control links are part of the approval snapshot.** Control status already was; since links now decide whether a mitigation counts, `build_snapshot` records each control's linked threats and hazard causes, so relinking makes an approved risk assessment stale. Existing approved risk assessments are marked stale once, on the next staleness run, because the snapshot gained these fields.

## Consequences

- Product risk ratios drop for existing mitigations without implemented controls; that is the point.
- A target date and owner per control (a plan with a deadline) is deferred; it needs a migration.
