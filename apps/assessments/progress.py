"""Questionnaire progress: how many active questions still need an answer.

Feeds the progress widget on the questionnaire page and the "Questions"
bars on the product page and the Compliance Overview. See
docs/architecture.md, "Dashboards".
"""

from .resolution import resolve_answers


def is_open(resolved_answer) -> bool:
    """An active question still needs work when it has no value (neither
    answered nor derived) or carries a carried-forward answer nobody has
    confirmed yet.
    """
    return resolved_answer.value in (None, "") or resolved_answer.needs_confirmation


def questionnaire_progress(configuration, resolved=None) -> dict:
    """Counts over the configuration's active questions (the ones its
    approved packages ask whose conditions currently hold).

    ``done`` + ``unanswered`` + ``needs_confirmation`` == ``total``;
    ``derived`` is the subset of ``done`` filled from ``implied_by``.
    """
    if resolved is None:
        resolved, _packages = resolve_answers(configuration)
    unanswered = needs_confirmation = derived = 0
    for resolved_answer in resolved.values():
        if resolved_answer.value in (None, ""):
            unanswered += 1
        elif resolved_answer.needs_confirmation:
            needs_confirmation += 1
        elif resolved_answer.is_derived:
            derived += 1
    total = len(resolved)
    return {
        "total": total,
        "done": total - unanswered - needs_confirmation,
        "unanswered": unanswered,
        "needs_confirmation": needs_confirmation,
        "derived": derived,
        "open": unanswered + needs_confirmation,
    }
