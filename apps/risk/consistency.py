"""Cross-method consistency checks between a threat and the hazards its
safety/property-damage consequences link to.

Threat and hazard keep their own methods and scales; these checks are
the "consistency rules instead of merged numbers" from
docs/architecture.md, "Risk register" -> "Cross-method rules". Only
rules 1 and 2 are implemented here (rule 3, a control lowering a linked
hazard's cyber-cause likelihood, is a reviewer-confirmed manual edit —
there is no automatic recomputation to implement; rule 4, one rating per
applicable method per entry, is already how Rating's uniqueness works).
"""

from .models import ImpactCategory, TreatmentType
from .rating import evaluate_entry_rating

LINKED_IMPACT_CATEGORIES = (ImpactCategory.SAFETY, ImpactCategory.PROPERTY_DAMAGE)


def _issue(code, message):
    return {"code": code, "message": message}


def check_threat_hazard_consistency(threat) -> list[dict]:
    """Issues for a threat whose consequences link to hazard entries."""
    issues: list[dict] = []
    linked_consequences = [
        c
        for c in threat.consequences.all()
        if c.hazard_id and c.impact_category in LINKED_IMPACT_CATEGORIES
    ]
    if not linked_consequences:
        return issues

    accepted = {t.method_id for t in threat.treatments.filter(treatment_type=TreatmentType.ACCEPT)}
    threat_ratings = list(threat.ratings.all())

    for consequence in linked_consequences:
        hazard = consequence.hazard
        for hazard_rating in hazard.ratings.all():
            hazard_result = evaluate_entry_rating(hazard, hazard_rating.method)
            if hazard_result["acceptance"] == "must_treat" and accepted:
                issues.append(
                    _issue(
                        "unacceptable_linked_hazard",
                        f"'{threat.label}' is treated as accept, but its linked hazard "
                        f"'{hazard.label}' is rated '{hazard_result['level']}' (must_treat) "
                        f"under {hazard_rating.method.source}.",
                    )
                )

            for threat_rating in threat_ratings:
                for mapping in threat_rating.method.content.get("severity_mappings", []):
                    if mapping["to_method"] != hazard_rating.method.source:
                        continue
                    mapped_floor = mapping["mapping"].get(str(consequence.severity))
                    if mapped_floor is not None and hazard_rating.severity < mapped_floor:
                        issues.append(
                            _issue(
                                "severity_mapping_violation",
                                f"'{hazard.label}' severity {hazard_rating.severity} under "
                                f"{hazard_rating.method.source} is below the floor "
                                f"{mapped_floor} implied by '{threat.label}' consequence "
                                f"severity {consequence.severity} under "
                                f"{threat_rating.method.source}.",
                            )
                        )

    return issues
