"""Evaluates a risk catalog's triggers against an applicability context.

The context is the same shape as an assessment's resolved answers plus
triggered finding ids (see apps/risk/suggestions.py), so a catalog entry
can trigger off either, e.g. "Wi-Fi present" (an answer) or "dormant
radio" (a finding). See docs/architecture.md, "Suggestions from
applicability".
"""

from .ruleengine import evaluate


def triggered_entries(content: dict, context: dict) -> list[str]:
    """Entry ids whose trigger evaluates truthy against context. Entries
    with no trigger are never auto-suggested (manual-only)."""
    triggered = []
    for entry in content.get("entries", []):
        trigger = entry.get("trigger")
        if trigger is not None and evaluate(trigger, context):
            triggered.append(entry["id"])
    return triggered


def run_catalog_fixtures(content: dict) -> list[dict]:
    reports = []
    for fixture in content.get("fixtures", []):
        actual = triggered_entries(content, fixture["context"])
        expected = fixture.get("expected_triggered", [])
        errors = []
        if set(actual) != set(expected):
            errors.append(f"expected triggered={sorted(expected)}, got {sorted(actual)}")
        reports.append(
            {"id": fixture["id"], "passed": not errors, "errors": errors, "actual": actual}
        )
    return reports
