"""Portfolio-level risk metrics: the same exposure classes and risk matrices
as a product's Risk status, rolled up over every product the user can see,
plus two ageing views (docs/adr/0048-portfolio-risk-overview.md).

Read-only. Methods are still never merged: one matrix per method, and the
only cross-method unit is the acceptance class. Ages use what is stored:

* *Time since last change* counts the entry's own edits and its treatments'
  edits (ratings and consequences touch the entry, ADR 0048).
* *Open since* counts from the day the entry was added to the register,
  because the register does not record when a risk was first left
  unmitigated. An entry is open while its class after treatment is
  ``must treat`` or ``justify``, or it is unrated.
"""

from django.utils import timezone

from apps.products.models import Configuration

from .metrics import (
    CLASSES,
    _exposure,
    _has_treatment,
    _heatmaps,
    _product_entries,
    _segments,
    _states,
)

AGE_BUCKETS = (
    ("30 days or less", 0, 30),
    ("31–90 days", 31, 90),
    ("91–180 days", 91, 180),
    ("Over 180 days", 181, None),
)
OPEN_CLASSES = ("must_treat", "justify", "unrated")
OLDEST_LIMIT = 5


def last_change(entry):
    """When the entry or any of its treatments was last edited."""
    return max([entry.updated_at, *(t.updated_at for t in entry.treatments.all())])


def _bucket_index(days: int) -> int:
    for index, (_, low, high) in enumerate(AGE_BUCKETS):
        if days >= low and (high is None or days <= high):
            return index
    return len(AGE_BUCKETS) - 1


def age_chart(items) -> list[dict]:
    """Rows for a stacked bar per age bucket. ``items`` are (days, class)
    pairs; ``width`` is relative to the busiest bucket."""
    rows = [
        {"label": label, "counts": {c: 0 for c in (*CLASSES, "unrated")}}
        for label, _, _ in AGE_BUCKETS
    ]
    for days, cls in items:
        rows[_bucket_index(days)]["counts"][cls] += 1
    peak = max((sum(r["counts"].values()) for r in rows), default=0)
    for row in rows:
        row["total"] = sum(row["counts"].values())
        row["segments"] = _segments(row["counts"])
        row["width"] = round(row["total"] / peak * 100) if peak else 0
    return rows


def _days(now, then) -> int:
    return max((now - then).days, 0)


def portfolio_metrics(products) -> dict:
    now = timezone.now()
    all_states = []
    rows = []
    changed = []
    open_items = []
    for product in products:
        states = _states(_product_entries(product))
        configuration = (
            Configuration.objects.filter(software_release__product=product).order_by("pk").first()
        )
        product_open = []
        for state in states:
            entry = state["entry"]
            entry.product_name = product.name
            cls = state["residual_class"] or "unrated"
            changed.append((_days(now, last_change(entry)), cls))
            if cls in OPEN_CLASSES:
                item = {
                    "entry": entry,
                    "product": product,
                    "configuration": configuration,
                    "class": cls,
                    "days": _days(now, entry.created_at),
                }
                product_open.append(item)
        exposure = _exposure(states)
        rows.append(
            {
                "product": product,
                "rateable": len(states),
                "must_treat": exposure["residual"]["must_treat"],
                "unrated": sum(1 for s in states if not s["methods"]),
                "untreated": sum(
                    1 for s in states if s["inherent_class"] and not _has_treatment(s)
                ),
                "open": len(product_open),
                "oldest_open": max((i["days"] for i in product_open), default=None),
                "latest_change": min(
                    (_days(now, last_change(s["entry"])) for s in states), default=None
                ),
            }
        )
        open_items.extend(product_open)
        all_states.extend(states)

    exposure = _exposure(all_states)
    open_items.sort(
        key=lambda i: (-i["days"], CLASSES.index(i["class"]) if i["class"] in CLASSES else 9)
    )
    rows.sort(key=lambda r: (-r["must_treat"], -r["unrated"], r["product"].name))
    return {
        "products": rows,
        "product_count": len(rows),
        "rateable": len(all_states),
        "exposure": exposure,
        "heatmaps": _heatmaps(all_states),
        "changed_chart": age_chart(changed),
        "open_chart": age_chart([(i["days"], i["class"]) for i in open_items]),
        "open_total": len(open_items),
        "oldest": open_items[:OLDEST_LIMIT],
    }
