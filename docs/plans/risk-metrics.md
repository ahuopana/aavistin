# Plan: risk metrics

Status: phases 1–4 implemented (ADR 0032): metrics module, register page, product page, Compliance Overview columns and the governance line. Not built: trends (phase 5), control owner and target date (phase 6), the demo seed (phase 7), and the CSV export. Where the build differs from this plan, "Implemented" notes say how.

## 1. Goal and scope

Today the only risk number in the app is `risk_ratio`: the share of baseline threat and hazard entries whose treatments all end up acceptable (`apps.products.services`). It feeds the risk bar on the welcome dashboard, the product page and the Compliance Overview. It answers one question ("how much is done?") and hides most of what a product team or an approver needs to know.

This plan adds **metrics computed from the risk register**: how complete it is, how much risk it holds, whether the treatments are real, and whether the approved view is still current. It does not change how entries are rated or treated, and it does not add new rating methods.

I read "risk metrics" as reporting on the register. If you meant something else (a new scoring method, factor-based likelihood, or metrics about vulnerabilities), say so before phase 1; the plan would change.

**Implemented.** Decisions 1–4 and 6 were confirmed as proposed, and trends (decision 5) were left for later because the aim is the current status. The metrics are in `apps.risk.metrics`; `risk_ratio` delegates to it, which changes its count: scoped entries and deltas are now included, and dismissed suggestions are no longer counted. Metric 13 (accepted risks without a justification) counts every treatment that needs a justification under ADR 0028's rule, not only accepts. Metric 20 (review cadence) and E19 are not built.

**Related work in flight.** PR #29 (risk register authoring in the app, `claude/risk-register-editing`) changes `risk_ratio` so a mitigation counts only once its controls are in place, and adds `apps.risk.mitigation`. This plan builds on that code, so **phase 1 starts after #29 merges**. #29 also carries an ADR numbered 0030 (`0030-mitigation-needs-controls.md`) that now collides with main's `0030-matrix-logo-and-teal-palette.md`, so one of them needs renumbering. This plan assigns no ADR numbers; take the next free one when writing each, after checking open branches.

## 2. What the existing model allows

| Fact | Consequence for metrics |
| --- | --- |
| Levels (`high`, `medium`, `low`) are defined by each method's matrix, but `acceptance` is a fixed vocabulary: `accept`, `justify`, `must_treat` (`schemas/method.schema.json`). | Aggregate across methods by acceptance class, which every method has. Show a method's own level names only inside that method. No schema change needed. |
| Architecture: threat and hazard keep their own methods; "the link carries consistency rules instead of merged numbers". | No composite risk score. Never add or average severities across methods. |
| A configuration's view is baseline plus deltas (`register_for_configuration`). `risk_ratio` looks at the baseline only. | Metrics should be computed per configuration view. The product number is then a roll-up with a stated rule (section 4). |
| A threat's severity is derived from its worst consequence (`apps.risk.rating`). | Inherent exposure is computable for every rated entry; residual only where a treatment has a residual rating. |
| Approved `RiskAssessment` rows hold a frozen snapshot, including ratings and method versions. `simple_history` is on entries, treatments and controls. | Past values exist at approval points; there is no time series between approvals. Trends need stored metric snapshots (phase 5). |
| Controls have a status (`planned`, `implemented`, `verified`) and, via `apps.evidence`, linked evidence that can expire or be superseded. | Control and evidence metrics are available without new fields. Overdue controls need an owner and a target date, which are deferred by #29 and need a migration. |
| Background tasks exist (`django-tasks`, ADR 0007) with a small scheduler. | Nightly metric snapshots are feasible without new infrastructure. |

## 3. Metric catalogue

All counts are over the entries in one configuration view (threats and hazards unless noted). "Per method" means one number per applicable method, never summed.

**A. Completeness: is the register done?**

1. Entries with no rating under an applicable method, and the same as a share.
2. Rated entries with no treatment.
3. Assets with a missing CIA rating (assets are the input to threat severity).
4. Catalog suggestions still pending, and dismissed with a reason.
5. Threats with no consequence (severity cannot be derived).

**B. Exposure: how much risk is there?**

6. Entries per acceptance class (`must_treat`, `justify`, `accept`), inherent and residual. This is the main method-neutral number, and the basis for a stacked bar.
7. Per method: a heat map of the severity × likelihood grid with entry counts per cell, inherent and residual. It reuses the matrix mark from ADR 0030 as its visual language, drawn with HTML and CSS rather than a chart library.
8. The top entries by residual class, then by severity, then by likelihood. A list with links, capped (for example at 5).
9. Risk reduction: entries that moved to a lower acceptance class after treatment.
10. Open `must_treat` count: entries whose residual is still `must_treat`, or that have no residual. This is the "needs action" figure for dashboards.

**C. Treatment quality: are the treatments real?**

11. Treatment mix (mitigate, accept, transfer, avoid).
12. Mitigation state (`apps.risk.mitigation`): no controls, planned, in place.
13. Accepted risks above the `accept` class, with their justification present or missing. (The UI already requires a justification; this catches data entered through admin or older rows.)
14. Controls by status, and controls linked to no entry or cause.
15. Controls marked `verified` without current evidence (none linked, expired or superseded). Depends on the evidence models only, not on evidence UI.

**D. Currency and governance: can the approved view be relied on?**

16. Per configuration: latest risk assessment status (none, draft, approved), stale flag, and age since approval.
17. Method or catalog version in the snapshot behind the latest approved version of that package.
18. Cross-method findings from `apps.risk.consistency`: safety-relevant threats whose linked hazard is unacceptable, and severity-mapping violations.

**E. Later (needs new fields)**

19. Controls past a target date, and controls per owner. Needs `Control.owner` and `Control.target_date` (migration; deferred in #29).
20. Review cadence: entries not reviewed within N months. Needs a `last_reviewed` concept; not designed.

## 4. Design

**One module, pure functions.** `apps.risk.metrics` exposes `register_metrics(configuration) -> dict` built from the resolved view, plus `product_metrics(product)` that rolls the configurations up. Views and templates only format. `risk_ratio` becomes a thin call into it (same `(acceptable, total)` result, so every caller and test keeps working), which removes the second code path that decides what "acceptable" means.

**Roll-up rule for a product.** A product has several configurations, each with its own view. Proposed: the product-level number is the **worst configuration** for exposure metrics (an entry counts as open if it is open in any configuration it applies to, counted once by identity), and the **sum** for completeness. The product page also shows a per-configuration table, so the roll-up never hides which configuration is the problem. Alternatives: baseline only (today's behaviour, simplest, ignores deltas), or per configuration only (no roll-up). I recommend the worst-configuration rule.

**No composite score.** The portfolio needs something sortable; the sort key is the tuple (open `must_treat`, `justify` without justification, unrated), not a weighted sum. A weighted score would imply the methods share a scale, which the architecture rules out, and would invite arguments about weights that carry no information.

**Presentation.**

- Risk register page: a summary strip above the table (completeness bar, stacked acceptance-class bar for inherent and residual, open `must_treat` count) and the heat map per method in a collapsible section.
- Product page: the same strip for the product, plus the per-configuration table (metrics 1, 6, 10, 12, 16).
- Compliance Overview: keep the risk bar; add sortable columns "must treat" and "unrated". The sort stays worst-first (open `must_treat` first, then unrated).
- Welcome dashboard: unchanged, except the risk bar's tooltip and aria label name the open `must_treat` count.
- Every colour has a text equivalent (counts in the label and aria text); acceptance classes use the existing status colours, not the orange attention colour, which ADR 0030 reserves for risk emphasis only.
- Server-rendered, same as the other dashboards (architecture "Performance": cache or precompute only if cost shows up). Entry counts per product are in the tens or low hundreds, so live computation is fine for now.

**History (phase 5).** A `RiskMetricSnapshot` row (product, configuration or null, taken_at, trigger, payload JSON, method and catalog versions) written when a risk assessment is approved and by a nightly task. The payload is the output of `register_metrics`, so the snapshot never needs a second definition. The trend view draws step charts of open `must_treat`, unrated and acceptable share. Rows are never edited. Metrics defined later start their history at the day they are added; no backfill from `simple_history`, which cannot reproduce past method versions faithfully.

**Permissions.** Same as the existing dashboards: a user sees metrics for products they hold a role on. Nothing here writes to the register.

**Export.** A CSV of the current per-entry rows (label, type, per-method inherent and residual class, treatment, mitigation state) from the register page. A JSON endpoint is left until the API framework question (architecture, open questions) is settled.

## 5. Phasing

| Phase | Deliverable | Notes |
| --- | --- | --- |
| 0 | Merge #29; decide the open questions below; one ADR for the metric definitions and roll-up rule | The ADR fixes definitions so the UI, the export and the snapshots cannot drift. |
| 1 | `apps.risk.metrics` for A, B, C and the parts of D that need no new data; `risk_ratio` delegates to it; unit tests on the demo packages (`demo-widget-risks`, `demo-widget-safety`) | No UI. Tests assert each metric on small hand-built registers, including a delta that overrides a baseline entry and two methods on one entry. |
| 2 | Register page strip and heat map; product page strip and per-configuration table | Includes an e2e test through the real pages. |
| 3 | Compliance Overview columns and sort; dashboard tooltip text; User Guide section | User Guide gets definitions of every metric in plain words, since the numbers are only trustworthy if people know what they count. |
| 4 | Governance metrics (D 16–18) shown on the product page | Reads existing approval and consistency data. |
| 5 | `RiskMetricSnapshot`, approval hook, nightly task, trend view | Migration; scheduler command already exists. |
| 6 | `Control.owner` and `target_date`, overdue metric (E 19), evidence-backed `verified` metric if the evidence UI has landed | Own ADR and migration. Revisit the "in progress" bar segment deferred in #29. |
| 7 | Demo seed: Aavistin's register shows non-trivial metrics (some open, some unrated, one stale) | Seed already planned in the architecture doc's demo section. |

Phases 1–3 are the useful first release; 4–7 can be reordered or dropped on feedback.

## 6. Decisions to confirm

1. **Scope reading** (section 1): metrics over the register, no new scoring methods.
2. **Roll-up rule** (section 4): worst configuration, with a per-configuration table. Alternatives: baseline only, or no roll-up.
3. **No composite score:** sort by the tuple, not a weighted sum.
4. **Acceptance class as the cross-method unit**, with level names only within a method.
5. **History:** store snapshots going forward, no backfill (phase 5). Do you want trends in the first release, or can they wait?
6. **Heat map without a chart library**, using HTML and CSS only.

## 7. Risks and open questions

- **Metrics that look precise but aren't.** Counts depend on how complete the register is: a product with three entries and all acceptable scores better than a thorough product with a few open items. The completeness metrics sit next to the exposure ones for this reason, and the roll-up never shows an exposure number without the entry count behind it.
- **Gaming.** Accepting a risk with a one-word justification clears it from `must_treat`. Metric 13 and an approver's review are the only guards; the separation-of-duties policy (milestone 2) applies to approval, not to editing.
- **Entry granularity.** PR #29 creates one threat per violated property, so one underlying scenario can appear as three entries. Counts may overstate scenarios; the metric labels say "entries", not "risks". If this proves misleading, group by a shared origin once entries record one.
- **Safety and security shown together.** A single "open must-treat" count mixes hazards and threats. The strip shows both the total and the split by entry type.
- **Dated or regulation-specific views.** "Open must-treat for the CRA only" needs entries to know which regulation required them (catalog source gives a partial answer). Not in scope; noted for when per-regulation reporting is designed.
- **Cost at scale.** If a portfolio of hundreds of products makes live computation slow, move the Compliance Overview to the latest `RiskMetricSnapshot` (phase 5) instead of recomputing, accepting up to a day of staleness there only.
