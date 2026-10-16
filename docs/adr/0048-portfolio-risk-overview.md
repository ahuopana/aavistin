# 48. Portfolio risk overview and ageing

Status: Accepted

## Context

Risk metrics (ADR 0046) are shown per configuration and per product. Someone responsible for several products had to open each one to see where risk stands, and nothing showed how long risks had waited: a register can look healthy while its open risks have not been touched for a year.

## Decisions

- **One page, `Risk`, in the main navigation** (`core:risk_overview`), over the products the user holds a role on (the same set as the Compliance Overview). It reuses the exposure classes, the class bars and the risk matrices of ADR 0046; the numbers come from `apps.risk.portfolio`, which only combines what `apps.risk.metrics` already computes.
- **Matrices stay per method.** Entries from different products are placed on the grid of the method package they are rated under. A cell's tooltip names the product with each entry. No severity is added across methods and there is no portfolio score; the only cross-method unit is the acceptance class.
- **Two ageing views, stacked by class after treatment, in four buckets** (30 days or less, 31–90, 91–180, over 180):
  - *Time since last change*: the latest of the entry's `updated_at` and its treatments' `updated_at`. Ratings and consequences have no timestamp of their own, so saving or removing one now touches the entry's `updated_at`.
  - *Open risks by age*: an entry is open while its class after treatment is `must treat` or `justify`, or it is unrated. Its age counts from `created_at`. The register does not record when a risk was first left unmitigated, so "added to the register" stands in for it. Storing the date a treatment became effective would give a truer figure and is left for later.
- **Charts are server-rendered HTML and CSS**, the same approach as the class bars: each bar has a text label and count, a table version sits under each chart, and class colours always come with a glyph.
- **The risk bars link to the Risk status tab** of the product (`?tab=risk`), the way the compliance bar links to its breakdown.

## Consequences

- The page loads every visible product's register, so it is as heavy as the Compliance Overview. If portfolios grow large it can be cached or computed in the background.
- The ageing figures are approximations until treatments record when they took effect; the page says so beside each chart.
