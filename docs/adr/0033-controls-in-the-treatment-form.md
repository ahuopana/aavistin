# 33. Controls are picked in the treatment form

Status: Accepted. Refines ADR 0031.

## Context

ADR 0031 requires a *mitigate* treatment to have at least one control: the control is the plan. The treatment form said so, but controls were linked in a separate section further down the page. Saving the treatment first only produced an error after a reload.

## Decision

- The treatment form shows a **"How is it mitigated?"** block when the treatment is *mitigate*. For a threat, it lists the product's controls with the threat's current links ticked. For a hazard, it lists them per cause. A new control can be named there (with its status, and for a hazard its cause).
- Saving applies the picks and creates the new control, then validates the treatment, **in one transaction**: if the treatment is invalid, no control or link is kept. A threat's picks replace its control links. A hazard's picks are set per cause.
- The picks only apply when the form carries the block (`controls_form`), so other callers cannot unlink controls by accident.
- The treatment summary lists the controls behind a mitigation, with status and evidence count. The section below becomes **"All controls for this threat"**: an overview to change status, unlink, or link more. Controls belong to the threat, so the same picks count for every method's mitigation.

## Consequences

- No model change. ADR 0031's rules (at least one control; residual counts once controls are in place) are unchanged.
