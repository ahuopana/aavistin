"""Shared question library: questions declared once, used by many packages.

A ``question_set`` package holds canonical question definitions (type,
level, label, guidance) so that requirement packages reference them with
``uses: ["<set-source>:<question_id>"]`` instead of redeclaring them. A
question may also declare ``implied_by``: when no explicit answer exists,
its value is derived from other answers (see
apps/assessments/resolution.py). See docs/adr/0015-shared-question-library.md.
"""

from .models import PackageKind, PackageStatus, RequirementPackage
from .ruleengine import RuleEngineError, evaluate


def library_questions(*, exclude_source: str | None = None, approved_only: bool = False) -> dict:
    """Question id -> definition, from the newest version of each question set.

    Each definition carries a ``_set`` key naming the declaring set's source.
    ``approved_only`` restricts to approved versions (used at resolution time).
    """
    packages = RequirementPackage.objects.filter(kind=PackageKind.QUESTION_SET)
    if approved_only:
        packages = packages.filter(status=PackageStatus.APPROVED)
    if exclude_source:
        packages = packages.exclude(source=exclude_source)
    newest: dict[str, RequirementPackage] = {}
    for package in packages.order_by("imported_at", "pk"):
        newest[package.source] = package
    questions: dict[str, dict] = {}
    for source, package in newest.items():
        for question in package.content.get("questions", []):
            questions.setdefault(question["id"], {**question, "_set": source})
    return questions


def not_carried_forward() -> set[str]:
    """Ids of approved questions declaring ``carry_forward: false`` (ADR 0021)."""
    ids = {
        qid
        for qid, q in library_questions(approved_only=True).items()
        if q.get("carry_forward") is False
    }
    for content in RequirementPackage.objects.filter(
        kind=PackageKind.REQUIREMENT, status=PackageStatus.APPROVED
    ).values_list("content", flat=True):
        ids.update(
            q["id"] for q in content.get("questions", []) if q.get("carry_forward") is False
        )
    return ids


def derive_value(question: dict, data: dict):
    """The value ``question.implied_by`` derives from ``data``, or None."""
    implied = question.get("implied_by")
    if implied is None:
        return None
    try:
        return implied["value"] if evaluate(implied["when"], data) else None
    except RuleEngineError:
        return None


def run_question_set_fixtures(content: dict) -> list[dict]:
    """Each fixture gives explicit answers and the derived values expected."""
    questions = {q["id"]: q for q in content.get("questions", [])}
    reports = []
    for fixture in content.get("fixtures", []):
        data = dict(fixture.get("answers", {}))
        for _ in range(len(questions) + 1):
            changed = False
            for qid, question in questions.items():
                if qid in data:
                    continue
                value = derive_value(question, data)
                if value is not None:
                    data[qid] = value
                    changed = True
            if not changed:
                break
        errors = [
            f"expected {qid}={want!r}, got {data.get(qid)!r}"
            for qid, want in fixture.get("expected", {}).items()
            if data.get(qid) != want
        ]
        reports.append(
            {"id": fixture["id"], "passed": not errors, "errors": errors, "actual": data}
        )
    return reports
