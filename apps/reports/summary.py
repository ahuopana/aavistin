"""The report's summary tables: counts over the content that is printed.

A pure function of the content dict, so a stored report always summarises
exactly what it contains. Each group is ``{"title", "rows": [{"label",
"value", "tone"}]}``; ``tone`` colours the value (action_required, caution,
info, ok) like the finding badges.
"""

from collections import Counter

from apps.assessments.templatetags.assessment_tags import choice_label

# Acceptance values are defined by each method; these are only for ordering.
ACCEPTANCE_ORDER = ["must_treat", "justify", "accept"]
TONES = {"must_treat": "action_required", "justify": "caution", "accept": "ok"}


def _row(label, value, tone=""):
    return {"label": label, "value": value, "tone": tone}


def _by_acceptance(counter: Counter):
    ordered = sorted(
        counter, key=lambda a: ACCEPTANCE_ORDER.index(a) if a in ACCEPTANCE_ORDER else 99
    )
    return [_row(choice_label(a), counter[a], TONES.get(a, "")) for a in ordered]


def _assessment(a):
    findings = Counter(f["level_id"] for f in a["findings"])
    outside = sum(1 for f in a["findings"] if f["out_of_scope"])
    in_scope = sum(1 for r in a["results"] if r["in_scope"])
    out_of_scope = a["out_of_scope_count"]
    rows = [
        _row("Regulations in scope", in_scope),
        _row("Regulations out of scope", out_of_scope),
        _row("Requirements in force", sum(len(r["requirements"]) for r in a["results"])),
        _row("Findings: action required", findings["action_required"], "action_required"),
        _row("Findings: caution", findings["caution"], "caution"),
        _row("Findings: info", findings["info"], "info"),
    ]
    if outside:
        rows.append(_row("Findings of out-of-scope regulations", outside))
    rows += [
        _row("Questions answered", len(a["answers"])),
        _row(
            "Answers needing confirmation", sum(1 for x in a["answers"] if x["needs_confirmation"])
        ),
    ]
    return {"title": "Assessment", "rows": rows}


def _risks(r):
    types = Counter(e["type"] for e in r["entries"])
    ratings = Counter(
        x["acceptance"] for e in r["entries"] for x in e["ratings"] if x.get("acceptance")
    )
    rows = [_row(f"{kind}s", count) for kind, count in sorted(types.items())] or [
        _row("Entries", 0)
    ]
    if ratings:
        rows.append(_row("Rated, by acceptance", ""))
        rows += _by_acceptance(ratings)
    return {"title": "Risks", "rows": rows}


def _mitigations(m):
    treatments = Counter(t["treatment"] for t in m["treatments"])
    residual = Counter(
        t["residual"]["acceptance"] for t in m["treatments"] if t["residual"].get("acceptance")
    )
    controls = Counter(k["status"] for k in m["controls"])
    rows = [
        _row(f"Treatments: {choice_label(t).lower()}", n) for t, n in sorted(treatments.items())
    ]
    rows = rows or [_row("Treatments", 0)]
    if residual:
        rows.append(_row("Residual rating, by acceptance", ""))
        rows += _by_acceptance(residual)
    rows.append(_row("Controls", len(m["controls"])))
    rows += [_row(f"Controls: {choice_label(s).lower()}", n) for s, n in sorted(controls.items())]
    rows.append(
        _row("Controls without evidence", sum(1 for k in m["controls"] if not k["evidence_count"]))
    )
    return {"title": "Mitigations", "rows": rows}


def _evidence(items):
    return {
        "title": "Evidence",
        "rows": [
            _row("Records", len(items)),
            _row("Files (with checksum)", sum(1 for e in items if e["sha256"])),
            _row("Expired", sum(1 for e in items if e["expired"]), "caution"),
            _row("Superseded", sum(1 for e in items if e["superseded"]), "info"),
        ],
    }


def build_summary(content: dict) -> list[dict]:
    groups = []
    if content.get("assessment"):
        groups.append(_assessment(content["assessment"]))
    if content.get("risks"):
        groups.append(_risks(content["risks"]))
    if content.get("mitigations"):
        groups.append(_mitigations(content["mitigations"]))
    if "evidence" in content.get("sections", []):
        groups.append(_evidence(content["evidence"]))
    return groups
