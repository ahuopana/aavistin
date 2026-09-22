"""Evaluates a Configuration's active packages against its resolved answers.

Produces, per package: in/out of scope, matched classifications, the
requirements and assessment routes that apply, and any findings —
before a snapshot is ever taken (see docs/architecture.md, "Products and
assessments", "Findings" and "Results").
"""

from apps.packages.fixtures_runner import evaluate_scope
from apps.packages.ruleengine import evaluate

from .resolution import resolve_answers


def evaluate_configuration(configuration, resolved=None, packages=None) -> dict:
    if resolved is None or packages is None:
        resolved, packages = resolve_answers(configuration)

    data = {question_id: ra.value for question_id, ra in resolved.items()}

    results = []
    findings = []
    for package in packages:
        content = package.content
        in_scope = evaluate_scope(content, data)

        classification_ids = []
        for classification in content.get("classifications", []):
            condition = classification.get("when")
            if condition is None or evaluate(condition, data):
                classification_ids.append(classification["id"])

        extended_data = {**data, **{f"class__{cid}": True for cid in classification_ids}}

        package_findings = []
        for rule in content.get("finding_rules", []):
            if evaluate(rule.get("when", False), extended_data):
                package_findings.append(
                    {
                        "id": rule["id"],
                        "level": rule["level"],
                        "message": rule["message"],
                        "ref": rule.get("ref"),
                        "source": package.source,
                        "version": package.version,
                    }
                )
        findings.extend(package_findings)

        requirements = []
        if in_scope:
            for requirement in content.get("requirements", []):
                applies_to = requirement.get("applies_to_classes")
                if not applies_to or set(applies_to) & set(classification_ids):
                    requirements.append(requirement["id"])

        routes = [
            route["id"]
            for route in content.get("assessment_routes", [])
            if evaluate(route.get("allowed_when", True), extended_data)
        ]

        results.append(
            {
                "source": package.source,
                "version": package.version,
                "package_id": package.pk,
                "package_type": package.package_type,
                "creates_legal_obligations": package.creates_legal_obligations,
                "in_scope": in_scope,
                "classifications": classification_ids,
                "requirements": requirements,
                "assessment_routes": routes,
            }
        )

    resolved_answers = {
        question_id: {
            "value": ra.value,
            "needs_confirmation": ra.needs_confirmation,
            "origin": ra.origin,
        }
        for question_id, ra in resolved.items()
    }

    return {"resolved_answers": resolved_answers, "results": results, "findings": findings}
