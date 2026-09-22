"""Resolves the effective answer for each active question of a Configuration.

Walks the precedence chain (option -> SW release -> HW revision ->
product) per docs/architecture.md, "Answer inheritance", and filters the
questionnaire by target market (only packages for the hardware variant's
selected markets are active) and by each question's own condition
(evaluated against answers already resolved).
"""

from dataclasses import dataclass
from typing import Any

from apps.packages.models import PackageStatus, RequirementPackage
from apps.packages.ruleengine import evaluate

from .models import Answer

PRECEDENCE = ["software_option", "software_release", "hardware_revision", "product"]


@dataclass
class ResolvedAnswer:
    question: dict
    answer: Answer | None

    @property
    def value(self) -> Any:
        return self.answer.value if self.answer is not None else None

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.answer and self.answer.needs_confirmation)

    @property
    def origin(self) -> str | None:
        return self.answer.owner_level if self.answer is not None else None


def active_packages(configuration):
    """Approved packages whose jurisdiction matches the configuration's target markets."""
    market_codes = set(
        configuration.hardware_revision.hardware_variant.target_markets.values_list(
            "code", flat=True
        )
    )
    if not market_codes:
        return RequirementPackage.objects.none()
    return RequirementPackage.objects.filter(
        status=PackageStatus.APPROVED, jurisdiction__in=market_codes
    )


def package_questions(packages) -> dict[str, dict]:
    """Union of question definitions across packages, deduplicated by id
    (questions are shared across packages; first-seen definition wins)."""
    questions: dict[str, dict] = {}
    for package in packages:
        for question in package.content.get("questions", []):
            questions.setdefault(question["id"], question)
    return questions


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
            resolved[question_id] = ResolvedAnswer(question=question, answer=answer)
            resolved_this_pass.append(question_id)
        if not resolved_this_pass:
            break
        for question_id in resolved_this_pass:
            del pending[question_id]

    return resolved, packages
