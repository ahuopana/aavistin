"""Computes a register entry's severity/likelihood/level/acceptance per method.

A hazard's severity is rated directly; a threat's severity is derived —
the worst of its consequences (see docs/architecture.md, "Assets and
threats": "The threat's severity is the worst consequence").
"""

from apps.packages.method_engine import evaluate_matrix

from .models import EntryType


def threat_severity(threat) -> int | None:
    consequences = list(threat.consequences.all())
    if not consequences:
        return None
    return max(c.severity for c in consequences)


def evaluate_entry_rating(entry, method) -> dict:
    """Returns {severity, likelihood, level, acceptance} for entry under method.

    Any field is None if the entry isn't rated (yet) for that method.
    """
    rating = entry.ratings.filter(method=method).first()
    if rating is None:
        return {"severity": None, "likelihood": None, "level": None, "acceptance": None}

    severity = rating.severity if entry.entry_type == EntryType.HAZARD else threat_severity(entry)
    if severity is None:
        return {
            "severity": None,
            "likelihood": rating.likelihood,
            "level": None,
            "acceptance": None,
        }

    matrix_result = evaluate_matrix(method.content, severity, rating.likelihood)
    return {"severity": severity, "likelihood": rating.likelihood, **matrix_result}


def evaluate_residual_rating(treatment) -> dict:
    """Returns {level, acceptance} for a treatment's residual severity/likelihood."""
    if treatment.residual_severity is None or treatment.residual_likelihood is None:
        return {"level": None, "acceptance": None}
    return evaluate_matrix(
        treatment.method.content, treatment.residual_severity, treatment.residual_likelihood
    )
