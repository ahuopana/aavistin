# 32. Navigation and workflow guidance

Status: Accepted

## Context

The usability analysis in `docs/usability/2026-10-navigation-analysis.md` found that pages below the product had no way back to it, the next task after the questionnaire was hidden, approvers had no worklist, risk-register approval existed only in Django admin, and the level a question is answered at (product, hardware, software, option) was invisible. None of this is covered by `docs/architecture.md`.

## Decision

- **Breadcrumbs** (`apps.core.navigation.breadcrumbs`, `templates/core/_breadcrumb.html`) on every page below the portfolio. The product family has no page of its own; its crumb links to its anchor on the portfolio.
- **Workflow per configuration** (`configuration_workflow`): four steps (Questions, Assessment, Risk register, Approval) and one next step for the current user, computed on each request from existing data, never stored. A step another role must do is shown as "waiting", not as a button. Shown as a bar on the questionnaire, assessment and risk register, and as chips in the product's Configurations tab.
- **Approval worklist** (`approval_items`): draft entities, draft or stale assessments, and unapproved or stale risk registers (with entries) in products where the user is an approver. Shown on an Approvals page, a nav link for approvers (context processor) and a dashboard widget.
- **Risk register approval in the app**: `risk:approve` approves the latest draft `RiskAssessment` or creates one, using the existing `approve_risk_assessment`. Earlier snapshots stay as history. No separation-of-duties check, as before (the admin action had none either).
- **Approval check**: the assessment page summarises open questions, findings, risk state and the separation-of-duties outcome before the approve button. With open questions, approval needs an explicit confirmation (`confirm_open`), enforced in the view. It is a guard, not a block: approving early stays possible on purpose.
- **Question ownership**: each question shows its level and the entity its answer is stored on; the questionnaire filters by level; option-level answers let the editor pick the option when a configuration has several; the server checks that the chosen entity belongs to the configuration. The product page links to level-filtered questionnaires per HW revision, SW release and option. There is still one Editor role; splitting it into hardware and software editors is not done.
- **Roles at product scope** in the assessment views, as in the product and risk views, so product-level grants work there too.
- **Slugs** are derived from names when left empty (unique among siblings with a numeric suffix), which resolves the deferral in ADR 0015.

## Consequences

- The workflow and worklist evaluate progress and the register per configuration on each request. Fine at current data volumes; revisit with caching or precomputation if portfolios grow (see "Performance" in the architecture).
- The Organisation page stays separate from the Portfolio; merging them is deferred.
