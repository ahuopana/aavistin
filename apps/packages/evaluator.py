"""Evaluates one requirement package's content against a set of answers.

Pure: no database access. Used by package fixtures (apps.packages.fixtures_runner)
and by assessments (apps.assessments.evaluation), so both run the same rules.
See docs/adr/0019-requirement-applicability.md.
"""

from datetime import date

from .ruleengine import evaluate

CLASSIFICATION_VAR_PREFIX = "class__"


def evaluate_scope(content: dict, answers: dict) -> bool:
    scope = content.get("scope", {})
    if not evaluate(scope.get("include", False), answers):
        return False
    return not any(
        evaluate(exclusion.get("when", False), answers) for exclusion in scope.get("exclude", [])
    )


def _requirement_status(requirement: dict, *, as_of: date | None) -> str:
    """'in_force', 'upcoming' or 'ended', against the assessment date.

    Without ``as_of`` (fixtures that don't set one) calendar dates are ignored.
    """
    if as_of is None:
        return "in_force"
    start, end = requirement.get("applies_from"), requirement.get("applies_until")
    if start and as_of < date.fromisoformat(start):
        return "upcoming"
    if end and as_of >= date.fromisoformat(end):
        return "ended"
    return "in_force"


def evaluate_package(content: dict, answers: dict, *, as_of: date | None = None) -> dict:
    in_scope = evaluate_scope(content, answers)

    classifications = [
        c["id"]
        for c in content.get("classifications", [])
        if c.get("when") is None or evaluate(c["when"], answers)
    ]
    extended = {
        **answers,
        **{f"{CLASSIFICATION_VAR_PREFIX}{cid}": True for cid in classifications},
    }

    role_expression = content.get("role")
    role = evaluate(role_expression, answers) if role_expression is not None else None

    findings = [
        rule
        for rule in content.get("finding_rules", [])
        if evaluate(rule.get("when", False), extended)
    ]

    requirements: list[str] = []
    upcoming: list[dict] = []
    ended: list[dict] = []
    if in_scope:
        for requirement in content.get("requirements", []):
            classes = requirement.get("applies_to_classes")
            if classes and not set(classes) & set(classifications):
                continue
            roles = requirement.get("roles")
            if role is not None and roles and role not in roles:
                continue
            condition = requirement.get("applies_when")
            if condition is not None and not evaluate(condition, extended):
                continue
            status = _requirement_status(requirement, as_of=as_of)
            if status == "upcoming":
                upcoming.append(
                    {"id": requirement["id"], "applies_from": requirement["applies_from"]}
                )
            elif status == "ended":
                ended.append(
                    {"id": requirement["id"], "applies_until": requirement["applies_until"]}
                )
            else:
                requirements.append(requirement["id"])

    routes = [
        route["id"]
        for route in content.get("assessment_routes", [])
        if evaluate(route.get("allowed_when", True), extended)
    ]

    return {
        "in_scope": in_scope,
        "classifications": classifications,
        "role": role,
        "findings": findings,
        "requirements": requirements,
        "upcoming_requirements": upcoming,
        "ended_requirements": ended,
        "assessment_routes": routes,
    }
