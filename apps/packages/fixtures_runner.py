"""Runs a package's own test fixtures against its rules.

Every package carries example products with expected outcomes (see
docs/architecture.md, "Requirement sources"); these must pass before a
package can be approved. A fixture may check scope, findings,
classifications, assessment routes and in-force requirements (the last
needs ``as_of``, see docs/adr/0019-requirement-applicability.md).
"""

from datetime import date

from .evaluator import evaluate_package, evaluate_scope
from .question_sets import derive_value
from .ruleengine import RuleEngineError

__all__ = ["evaluate_scope", "evaluate_findings", "run_fixtures"]

LIST_EXPECTATIONS = ("findings", "classifications", "assessment_routes", "requirements")


def evaluate_findings(content: dict, answers: dict) -> list[str]:
    return [rule["id"] for rule in evaluate_package(content, answers)["findings"]]


def _with_derived(content: dict, answers: dict) -> dict:
    """Apply the package's own ``implied_by`` rules to a fixpoint, as answer
    resolution does (library questions need the database and are not derived
    here; a fixture states those answers explicitly)."""
    data = dict(answers)
    questions = [q for q in content.get("questions", []) if "implied_by" in q]
    for _ in range(len(questions) + 1):
        changed = False
        for question in questions:
            if data.get(question["id"]) is not None:
                continue
            value = derive_value(question, data)
            if value is not None:
                data[question["id"]] = value
                changed = True
        if not changed:
            break
    return data


def run_fixtures(content: dict) -> list[dict]:
    """Return one report entry per fixture: {id, passed, errors, actual}."""
    reports = []
    for fixture in content.get("fixtures", []):
        answers = _with_derived(content, fixture.get("answers", {}))
        expected = fixture.get("expected", {})
        as_of = fixture.get("as_of")
        errors = []
        actual = {}
        try:
            result = evaluate_package(
                content, answers, as_of=date.fromisoformat(as_of) if as_of else None
            )
        except (RuleEngineError, ValueError) as exc:
            errors.append(str(exc))
            reports.append(
                {"id": fixture["id"], "passed": False, "errors": errors, "actual": actual}
            )
            continue

        actual = {
            "in_scope": result["in_scope"],
            "findings": [rule["id"] for rule in result["findings"]],
            "classifications": result["classifications"],
            "assessment_routes": result["assessment_routes"],
            "requirements": result["requirements"],
        }
        if "in_scope" in expected and expected["in_scope"] != actual["in_scope"]:
            errors.append(f"expected in_scope={expected['in_scope']}, got {actual['in_scope']}")
        for key in LIST_EXPECTATIONS:
            if key in expected and set(expected[key]) != set(actual[key]):
                errors.append(f"expected {key}={sorted(expected[key])}, got {sorted(actual[key])}")

        reports.append(
            {"id": fixture["id"], "passed": not errors, "errors": errors, "actual": actual}
        )
    return reports
