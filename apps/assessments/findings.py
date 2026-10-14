"""Findings with what the user needs to act on them (ADR 0035).

An evaluation stores each finding as ``{id, level, message, ref, source,
version}``. For display, the finding is joined back to its rule in the
package version that raised it, adding the rule's optional ``guidance`` and
the questions its ``when`` expression reads (with their answers), so the user
sees why the finding was raised and where to change it.
"""

from apps.packages.linting import referenced_questions
from apps.packages.models import PackageKind, RequirementPackage

LEVEL_ORDER = {"action_required": 0, "caution": 1, "info": 2}


def _rules(findings) -> dict[tuple[str, str, str], dict]:
    keys = {(f["source"], f["version"]) for f in findings}
    if not keys:
        return {}
    packages = RequirementPackage.objects.filter(
        kind=PackageKind.REQUIREMENT,
        source__in={source for source, _ in keys},
        version__in={version for _, version in keys},
    )
    return {
        (package.source, package.version, rule["id"]): rule
        for package in packages
        if (package.source, package.version) in keys
        for rule in package.content.get("finding_rules", [])
    }


def finding_details(findings, resolved_answers=None, questions=None, results=None) -> list[dict]:
    """``findings`` most severe first, each with ``guidance``, ``based_on``
    (``[{id, label, value, type}]`` for the questions the rule reads that
    have a resolved answer) and ``out_of_scope`` (its package's scope rule
    excludes the configuration, so the finding doesn't count against
    compliance). ``questions`` maps question ids to question definitions;
    ``resolved_answers`` and ``results`` are the evaluation's entries of the
    same names."""
    resolved_answers = resolved_answers or {}
    questions = questions or {}
    out_of_scope = {
        (r["source"], r["version"]) for r in results or [] if not r.get("in_scope", True)
    }
    rules = _rules(findings)
    details = []
    for finding in sorted(findings, key=lambda f: LEVEL_ORDER.get(f["level"], 9)):
        rule = rules.get((finding["source"], finding["version"], finding["id"]), {})
        question_ids = dict.fromkeys(referenced_questions(rule.get("when")))
        details.append(
            {
                **finding,
                "anchor": f"finding-{finding['source']}-{finding['id']}",
                "guidance": rule.get("guidance", ""),
                "out_of_scope": (finding["source"], finding["version"]) in out_of_scope,
                "based_on": [
                    {
                        "id": question_id,
                        "label": questions.get(question_id, {}).get("label") or question_id,
                        "type": questions.get(question_id, {}).get("type", ""),
                        "value": resolved_answers[question_id].get("value"),
                    }
                    for question_id in question_ids
                    if question_id in resolved_answers
                ],
            }
        )
    return details
