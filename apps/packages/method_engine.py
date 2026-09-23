"""Evaluates a risk method's severity x likelihood matrix and acceptance.

Shared between the method package's own fixtures and apps.risk, which
uses the same content to rate register entries. See
docs/architecture.md, "Risk assessment: methods and catalogs".
"""

from .ruleengine import evaluate


def evaluate_matrix(content: dict, severity: int, likelihood: int) -> dict:
    """Returns {"level": ..., "acceptance": ...} for (severity, likelihood).

    Rules are evaluated in order; the first whose 'when' matches (or that
    has no 'when' at all, the catch-all) wins.
    """
    data = {"s": severity, "l": likelihood}
    for rule in content.get("matrix", []):
        when = rule.get("when")
        if when is None or evaluate(when, data):
            level = rule["level"]
            return {"level": level, "acceptance": content.get("acceptance", {}).get(level)}
    return {"level": None, "acceptance": None}


def run_method_fixtures(content: dict) -> list[dict]:
    reports = []
    for fixture in content.get("fixtures", []):
        inputs = fixture["inputs"]
        expected = fixture.get("expected", {})
        actual = evaluate_matrix(content, inputs["s"], inputs["l"])
        errors = []
        if "level" in expected and expected["level"] != actual["level"]:
            errors.append(f"expected level={expected['level']!r}, got {actual['level']!r}")
        if "acceptance" in expected and expected["acceptance"] != actual["acceptance"]:
            errors.append(
                f"expected acceptance={expected['acceptance']!r}, got {actual['acceptance']!r}"
            )
        reports.append(
            {"id": fixture["id"], "passed": not errors, "errors": errors, "actual": actual}
        )
    return reports
