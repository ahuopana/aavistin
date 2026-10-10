# 32. Risk metrics: definitions and roll-up

Status: Accepted

## Context

The only risk figure was `risk_ratio` (acceptable entries over all baseline threats and hazards). It said how much was done, not how much risk was left, how complete the register was, or whether a treatment could be relied on. The plan is `docs/plans/risk-metrics.md`; this ADR fixes the definitions it left open. It adds reporting only: no new rating method, no new stored data.

## Decisions

- **One module defines every metric.** `apps.risk.metrics` computes them from the resolved register; views and templates only format. `apps.products.services.risk_ratio` calls into it, so "acceptable" has one definition (ADR 0031's rule: every treatment has an acceptable residual, and a mitigation counts only with its controls in place).
- **Aggregate by acceptance class, not by score.** Levels belong to a method, but every method maps its levels to `accept`, `justify` or `must_treat` (the method schema fixes that vocabulary). An entry takes its worst class across the methods it is rated under. Severities are never added or averaged across methods, and there is no composite score; lists sort by (still must treat, unrated).
- **Inherent and effective residual position.** Inherent is the rating before treatment (a threat's severity is its worst consequence). Residual is the treatment's residual rating when it can be relied on, and the inherent position otherwise: no treatment, a treatment without a residual rating, or a mitigation whose controls are not in place yet. "Still must treat" is the number of entries whose residual class is `must_treat`.
- **Unrated and incomplete are not classes.** An entry with no rating is *unrated*; one rated but with no derivable severity (a threat with no consequence) is *incomplete*. Both appear as "unrated" in bars.
- **Roll-up over configurations.** Each threat or hazard counts once at product level, if it applies to at least one configuration (the baseline when there are none), and a delta replaces the baseline entry it overrides. An entry's state does not depend on the configuration, so an entry is open at product level exactly when it is open wherever it applies; the product page also lists each configuration. This changes `risk_ratio`: before, scoped entries and deltas were left out, and dismissed suggestions were counted.
- **Currency.** A configuration's latest risk assessment is shown as none, draft, approved or approved-and-stale, with its age and any method or catalog whose newest approved version differs from the one in the snapshot.
- **Presentation.** Server-rendered HTML and CSS: stacked class bars, a severity × likelihood grid per method before and after treatment, a short "needs attention first" list. Every colour has a text or glyph equivalent; the grid cells carry the class glyph and a hoverable, focusable count. Status colours are used for classes; the orange attention colour of ADR 0030 stays on the existing risk ratio bar.

## Consequences

- Product risk ratios can change for products with scoped entries or dismissed suggestions.
- Each page that shows metrics reads the register once per configuration; with tens of entries per product that is fine, and the Compliance Overview uses only the cheap summary (`risk_summary`).
- Deferred: trends (stored metric snapshots written at approval and nightly), control owners and target dates with an overdue count, and review cadence. They need new tables or fields and are listed in the plan, phases 5 and 6.
