"""Whether a "mitigate" treatment is backed by controls, and whether they are
in place yet.

A mitigation is only a claim until a control says how the risk is reduced,
and only effective once that control is implemented: see
docs/adr/0031-mitigation-needs-controls.md. Accept, transfer and avoid
treatments are decisions, not plans, so they have no mitigation state.
"""

from .models import Control, ControlStatus, EntryType, TreatmentType

NO_CONTROLS = "no_controls"
PLANNED = "planned"
IN_PLACE = "in_place"

LABELS = {
    NO_CONTROLS: "no controls linked",
    PLANNED: "mitigation planned",
    IN_PLACE: "controls in place",
}


def mitigation_controls(entry) -> list[Control]:
    """Controls that mitigate ``entry``: a threat's own controls, or the
    controls on any of a hazard's causes."""
    if entry.entry_type == EntryType.THREAT:
        return list(entry.controls.all())
    if entry.entry_type == EntryType.HAZARD:
        return list(Control.objects.filter(hazard_causes__hazard=entry).distinct())
    return []


def mitigation_state(treatment, controls=None) -> str | None:
    """NO_CONTROLS, PLANNED (some control still planned) or IN_PLACE for a
    mitigate treatment; None for any other treatment type."""
    if treatment.treatment_type != TreatmentType.MITIGATE:
        return None
    if controls is None:
        controls = mitigation_controls(treatment.entry)
    if not controls:
        return NO_CONTROLS
    if any(c.status == ControlStatus.PLANNED for c in controls):
        return PLANNED
    return IN_PLACE


def treatment_counts(treatment, controls=None) -> bool:
    """Whether a treatment's residual rating may be relied on: always for a
    decision (accept, transfer, avoid), only with controls in place for a
    mitigation."""
    state = mitigation_state(treatment, controls)
    return state is None or state == IN_PLACE
