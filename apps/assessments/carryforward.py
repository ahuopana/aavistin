"""Copies answers forward to a new software release, as "needs confirmation".

Per docs/architecture.md, "Answer inheritance": "A new release copies
answers forward as 'needs confirmation'. Reviewers may confirm in bulk,
but must confirm actively."
"""

from apps.packages.question_sets import not_carried_forward

from .models import Answer


def copy_answers_forward(from_release, to_release, *, actor=None) -> list[Answer]:
    """Questions about one release's change (``carry_forward: false``, ADR
    0021) are skipped, so the new release starts them unanswered."""
    skip = not_carried_forward()
    created = []
    for answer in Answer.objects.filter(software_release=from_release).exclude(
        question_id__in=skip
    ):
        created.append(
            Answer.objects.create(
                software_release=to_release,
                question_id=answer.question_id,
                value=answer.value,
                override_justification=answer.override_justification,
                needs_confirmation=True,
                created_by=actor,
            )
        )
    return created


def confirm_answers(answers, *, actor=None) -> int:
    """Actively confirm carried-forward answers; returns the count confirmed."""
    count = 0
    for answer in answers:
        if answer.needs_confirmation:
            answer.needs_confirmation = False
            if actor is not None:
                answer._history_user = actor
            answer.save(update_fields=["needs_confirmation", "updated_at"])
            count += 1
    return count
