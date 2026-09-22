"""Runs a package's own test fixtures against its scope and finding rules.

Every package carries example products with expected outcomes (see
docs/architecture.md, "Requirement sources"); these must pass before a
package can be approved.
"""

from .ruleengine import RuleEngineError, evaluate


def evaluate_scope(content: dict, answers: dict) -> bool:
    scope = content.get("scope", {})
    included = bool(evaluate(scope.get("include", False), answers))
    if not included:
        return False
    for exclusion in scope.get("exclude", []):
        if evaluate(exclusion.get("when", False), answers):
            return False
    return True


def evaluate_findings(content: dict, answers: dict) -> list[str]:
    triggered = []
    for rule in content.get("finding_rules", []):
        if evaluate(rule.get("when", False), answers):
            triggered.append(rule["id"])
    return triggered


def run_fixtures(content: dict) -> list[dict]:
    """Return one report entry per fixture: {id, passed, errors, actual}."""
    reports = []
    for fixture in content.get("fixtures", []):
        answers = fixture.get("answers", {})
        expected = fixture.get("expected", {})
        errors = []
        actual = {}
        try:
            actual["in_scope"] = evaluate_scope(content, answers)
            actual["findings"] = evaluate_findings(content, answers)
        except RuleEngineError as exc:
            errors.append(str(exc))
            reports.append(
                {"id": fixture["id"], "passed": False, "errors": errors, "actual": actual}
            )
            continue

        if "in_scope" in expected and expected["in_scope"] != actual["in_scope"]:
            errors.append(f"expected in_scope={expected['in_scope']}, got {actual['in_scope']}")
        if "findings" in expected and set(expected["findings"]) != set(actual["findings"]):
            errors.append(
                f"expected findings={sorted(expected['findings'])}, "
                f"got {sorted(actual['findings'])}"
            )

        reports.append(
            {
                "id": fixture["id"],
                "passed": not errors,
                "errors": errors,
                "actual": actual,
            }
        )
    return reports
