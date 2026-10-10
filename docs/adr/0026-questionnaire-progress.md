# 26. Questionnaire progress on the assessment and compliance views

Status: Accepted

## Context

Users could not see how many questions a configuration's questionnaire still needed: the questionnaire page listed every active question, and the product page and Compliance Overview showed only the compliance and risk ratios.

## Decisions

- **"Done" means has a value and isn't awaiting confirmation.** A derived value (`implied_by`) counts as done — nobody has to type it. A carried-forward answer flagged `needs_confirmation` counts as open, since the architecture requires a reviewer to confirm it actively. An answer cleared to the empty string counts as unanswered.
- **Only active questions count.** Questions whose `condition` doesn't hold aren't asked, so they aren't owed; the total can therefore grow as answers activate conditional questions. The page says so rather than precomputing a worst-case total.
- **Product rollup sums per configuration.** A product-level answer shared by three configurations counts three times, matching how `compliance_ratio` already counts per configuration and because each configuration's questionnaire must be complete on its own for its assessment.
- **Computed live, no caching.** Same reasoning as the welcome dashboard and Compliance Overview ("Performance" in `docs/architecture.md`); it adds one `resolve_answers` pass per configuration next to the one `compliance_ratio` already does.

## Consequences

- The Compliance Overview still sorts by compliance, then risk; questions progress is shown but doesn't change the order.
- If per-request cost grows, `questions_ratio` and `compliance_ratio` can share one resolution pass per configuration.
