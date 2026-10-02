"""Resolves the effective answer for each active question of a Configuration.

Walks the precedence chain (option -> SW release -> HW revision ->
product) per docs/architecture.md, "Answer inheritance", and filters the
questionnaire by target market (only packages for the configuration's effective
markets are active, see Configuration.effective_market_codes) and by each question's own condition
(evaluated against answers already resolved).
"""

from dataclasses import dataclass
from typing import Any

from apps.packages.models import PackageKind, PackageStatus, RequirementPackage
from apps.packages.question_sets import derive_value, library_questions
from apps.packages.ruleengine import evaluate

from .models import Answer

PRECEDENCE = ["software_option", "software_release", "hardware_revision", "product"]


@dataclass
class ResolvedAnswer:
    question: dict
    answer: Answer | None
    # Set when no explicit answer exists but the question's ``implied_by``
    # rule derived one from other answers (shared question library).
    derived_value: Any = None

    @property
    def value(self) -> Any:
        if self.answer is not None:
            return self.answer.value
        return self.derived_value

    @property
    def is_derived(self) -> bool:
        return self.answer is None and self.derived_value is not None

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.answer and self.answer.needs_confirmation)

    @property
    def origin(self) -> str | None:
        if self.answer is not None:
            return self.answer.owner_level
        return "derived" if self.is_derived else None


def active_packages(configuration):
    """Approved packages whose jurisdiction matches the configuration's target markets."""
    market_codes = configuration.effective_market_codes()
    if not market_codes:
        return RequirementPackage.objects.none()
    return RequirementPackage.objects.filter(
        status=PackageStatus.APPROVED, jurisdiction__in=market_codes
    )


def package_questions(packages) -> dict[str, dict]:
    """Union of question definitions across packages, deduplicated by id
    (questions are shared across packages).

    A package's ``uses`` references resolve to the shared question
    library (approved question sets) and take precedence; packages that
    still declare a question themselves fall back to first-seen wins.
    Each question dict gains ``used_by``: the sources that ask it.
    """
    library = library_questions(approved_only=True)
    questions: dict[str, dict] = {}
    used_by: dict[str, list[str]] = {}
    for package in packages:
        if package.kind != PackageKind.REQUIREMENT:
            continue
        for ref in package.content.get("uses", []):
            question_id = ref.partition(":")[2]
            if question_id in library:
                questions.setdefault(question_id, library[question_id])
                used_by.setdefault(question_id, []).append(package.source)
        for question in package.content.get("questions", []):
            questions.setdefault(question["id"], question)
            used_by.setdefault(question["id"], []).append(package.source)
    return {
        qid: {**q, "used_by": sorted(set(used_by.get(qid, [])))} for qid, q in questions.items()
    }


def resolve_answer(configuration, question_id: str) -> Answer | None:
    for option in configuration.software_options.all().order_by("id"):
        answer = Answer.objects.filter(software_option=option, question_id=question_id).first()
        if answer is not None:
            return answer

    answer = Answer.objects.filter(
        software_release=configuration.software_release, question_id=question_id
    ).first()
    if answer is not None:
        return answer

    answer = Answer.objects.filter(
        hardware_revision=configuration.hardware_revision, question_id=question_id
    ).first()
    if answer is not None:
        return answer

    product = configuration.hardware_revision.hardware_variant.product
    return Answer.objects.filter(product=product, question_id=question_id).first()


def resolve_answers(configuration) -> tuple[dict[str, ResolvedAnswer], list[RequirementPackage]]:
    packages = list(active_packages(configuration))
    questions = package_questions(packages)

    resolved: dict[str, ResolvedAnswer] = {}
    pending = dict(questions)
    max_passes = len(questions) + 1
    for _ in range(max_passes):
        if not pending:
            break
        data = {qid: ra.value for qid, ra in resolved.items()}
        resolved_this_pass = []
        for question_id, question in pending.items():
            condition = question.get("condition")
            if condition is not None and not evaluate(condition, data):
                continue
            answer = resolve_answer(configuration, question_id)
            derived = None if answer is not None else derive_value(question, data)
            resolved[question_id] = ResolvedAnswer(
                question=question, answer=answer, derived_value=derived
            )
            resolved_this_pass.append(question_id)
        if not resolved_this_pass:
            break
        for question_id in resolved_this_pass:
            del pending[question_id]

    _apply_derived(resolved)
    return resolved, packages


def _apply_derived(resolved: dict[str, ResolvedAnswer]) -> None:
    """Fill unanswered questions from their ``implied_by`` rules, to a fixpoint
    so derivations can chain (the linter rejects cycles)."""
    for _ in range(len(resolved) + 1):
        data = {qid: ra.value for qid, ra in resolved.items() if ra.value is not None}
        changed = False
        for ra in resolved.values():
            if ra.answer is not None or ra.derived_value is not None:
                continue
            value = derive_value(ra.question, data)
            if value is not None:
                ra.derived_value = value
                changed = True
        if not changed:
            break
