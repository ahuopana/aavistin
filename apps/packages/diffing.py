"""Structural diff between two package versions' content.

Every import shows a diff against the previous version of the same
source before approval (see docs/architecture.md, "Requirement
sources"). This is a shallow, id-keyed diff — enough to review what
changed, not a general JSON diff.
"""

ID_KEYED_SECTIONS = [
    "questions",
    "classifications",
    "requirements",
    "assessment_routes",
    "finding_rules",
    "fixtures",
]


def _by_id(items):
    return {item["id"]: item for item in items}


def _diff_section(old_items, new_items):
    old_by_id, new_by_id = _by_id(old_items), _by_id(new_items)
    added = sorted(set(new_by_id) - set(old_by_id))
    removed = sorted(set(old_by_id) - set(new_by_id))
    changed = sorted(
        item_id
        for item_id in set(old_by_id) & set(new_by_id)
        if old_by_id[item_id] != new_by_id[item_id]
    )
    return {"added": added, "removed": removed, "changed": changed}


def diff_packages(old_content: dict, new_content: dict) -> dict:
    diff = {
        "version": {"from": old_content.get("version"), "to": new_content.get("version")},
        "sections": {},
    }
    for section in ID_KEYED_SECTIONS:
        section_diff = _diff_section(old_content.get(section, []), new_content.get(section, []))
        if any(section_diff.values()):
            diff["sections"][section] = section_diff

    if old_content.get("scope") != new_content.get("scope"):
        diff["scope_changed"] = True

    return diff
