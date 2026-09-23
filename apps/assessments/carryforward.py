"""Copies answers forward to a new software release, as "needs confirmation".

Per docs/architecture.md, "Answer inheritance": "A new release copies
answers forward as 'needs confirmation'. Reviewers may confirm in bulk,
but must confirm actively."
"""

from .models import Answer


def copy_answers_forward(from_release, to_release, *, actor=None) -> list[Answer]:
    created = []
    for answer in Answer.objects.filter(software_release=from_release):
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
