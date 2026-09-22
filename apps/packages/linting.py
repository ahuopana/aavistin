"""Semantic linter for requirement packages.

Runs after JSON Schema validation, which only checks shape. This checks
meaning: that a package doesn't reference a question it never declared,
that a rule uses an operator its question type supports, that dates make
sense, that supersedes chains don't loop, and that an unofficial package
can't silently take over an official package's namespace. See
docs/architecture.md, "Requirement sources" → "Import and sanity checks".
"""

from datetime import date

NUMERIC_OPS = {"<", "<=", ">", ">=", "+", "-", "*", "/"}


def _issue(severity, code, message, path=""):
    return {"severity": severity, "code": code, "path": path, "message": message}


def _iter_expressions(content):
    """Yield (path, expression) for every rule expression in the package."""
    scope = content.get("scope", {})
    if "include" in scope:
        yield "scope.include", scope["include"]
    for i, excl in enumerate(scope.get("exclude", [])):
        yield f"scope.exclude[{i}].when", excl.get("when")

    for i, q in enumerate(content.get("questions", [])):
        if "condition" in q:
            yield f"questions[{i}].condition", q["condition"]

    for i, c in enumerate(content.get("classifications", [])):
        if "when" in c:
            yield f"classifications[{i}].when", c["when"]

    for i, r in enumerate(content.get("assessment_routes", [])):
        if "allowed_when" in r:
            yield f"assessment_routes[{i}].allowed_when", r["allowed_when"]

    for i, f in enumerate(content.get("finding_rules", [])):
        yield f"finding_rules[{i}].when", f.get("when")


def _referenced_vars(expression, *, under_numeric_op=False):
    """Yield (question_id, under_numeric_op) for every {"var": ...} node."""
    if isinstance(expression, dict) and len(expression) == 1:
        op, args = next(iter(expression.items()))
        if op == "var":
            name = args[0] if isinstance(args, list) else args
            if isinstance(name, str):
                yield name, under_numeric_op
            return
        arg_list = args if isinstance(args, list) else [args]
        for sub in arg_list:
            yield from _referenced_vars(sub, under_numeric_op=(op in NUMERIC_OPS))
    elif isinstance(expression, list):
        for sub in expression:
            yield from _referenced_vars(sub, under_numeric_op=under_numeric_op)


def lint_package(content: dict, *, is_official: bool, existing_packages) -> list[dict]:
    """Return a list of lint issues; empty means clean.

    ``existing_packages`` is a RequirementPackage queryset (any status) to
    check namespace shadowing and supersedes cycles against.
    """
    issues: list[dict] = []
    question_types = {q["id"]: q["type"] for q in content.get("questions", [])}

    for path, expr in _iter_expressions(content):
        if expr is None:
            continue
        for question_id, under_numeric_op in _referenced_vars(expr):
            qtype = question_types.get(question_id)
            if qtype is None:
                issues.append(
                    _issue(
                        "error",
                        "unknown_question",
                        f"references undeclared question '{question_id}'",
                        path,
                    )
                )
            elif under_numeric_op and qtype != "number":
                issues.append(
                    _issue(
                        "error",
                        "type_mismatch",
                        f"question '{question_id}' is '{qtype}', not usable in a numeric "
                        "comparison",
                        path,
                    )
                )

    dates = content.get("dates_of_application") or {}
    date_from, date_until = dates.get("from"), dates.get("until")
    for label, value in (("from", date_from), ("until", date_until)):
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError:
                issues.append(
                    _issue(
                        "error",
                        "bad_date",
                        f"dates_of_application.{label} is not a valid ISO date: {value!r}",
                        "dates_of_application",
                    )
                )
    if date_from and date_until:
        try:
            if date.fromisoformat(date_from) > date.fromisoformat(date_until):
                issues.append(
                    _issue(
                        "error",
                        "date_order",
                        "dates_of_application.from is after dates_of_application.until",
                        "dates_of_application",
                    )
                )
        except ValueError:
            pass  # already reported above

    source = content.get("source")
    if not is_official and existing_packages.filter(source=source, is_official=True).exists():
        issues.append(
            _issue(
                "error",
                "namespace_shadow",
                f"source '{source}' is already used by an official package; a local "
                "package cannot shadow it",
                "source",
            )
        )

    self_ref = {"source": content.get("source"), "version": content.get("version")}
    seen = {(self_ref["source"], self_ref["version"])}
    frontier = list(content.get("supersedes", []))
    while frontier:
        ref = frontier.pop()
        key = (ref.get("source"), ref.get("version"))
        if key in seen:
            issues.append(
                _issue(
                    "error",
                    "supersedes_cycle",
                    f"supersedes chain loops back to {key[0]}@{key[1]}",
                    "supersedes",
                )
            )
            break
        seen.add(key)
        predecessor = existing_packages.filter(source=key[0], version=key[1]).first()
        if predecessor is not None:
            frontier.extend(predecessor.content.get("supersedes", []))

    return issues
