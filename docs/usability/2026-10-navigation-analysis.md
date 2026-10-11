# Aavistin usability analysis: navigation and task flow

## Update after implementation (2026-10-11)

The suggestions in section 6 were implemented on the same branch (ADR 0032), and the browser walkthrough was repeated as the editor (edna), the approver (ana) and the user with both roles (sam). In the re-run, the editor answered a hardware question through the product page's "Hardware questions" link; the remaining 80-odd questions were then filled by a script to save time. From there the editor followed only the workflow bar's "Next step" button to the first risk entry. The approver followed the Approvals page and the same button through assessment, risk register and configuration approval, until the bar said "All steps are complete". Every page below the portfolio now has a breadcrumb back to the product and the portfolio.

| # | Suggestion | Status |
| --- | --- | --- |
| P1.1 | Breadcrumb on every page below the portfolio | Solved. The family crumb links to its anchor on the portfolio; the family has no page of its own. |
| P1.2 | "Next step" workflow bar | Solved: on the questionnaire, assessment and risk register. Another role's step reads "Waiting for …". |
| P1.3 | Per-configuration status on the product page | Solved: step chips and the next step per configuration, plus equal Questions / Risk register / Assessment links. |
| P1.4 | Approver worklist | Solved: Approvals page, nav link for approvers, dashboard widget. |
| P1.5 | Readable labels in results | Solved: package titles; labels for classifications, requirements and routes; requirements folded by in force / upcoming / ended. |
| P2.6 | Question level and owner, level filter, per-level entry points | Solved: level badge with owner ("Hardware · EU variant rev A"), "Answered at" filter with open counts, Hardware / Software / Option / Product question links on the product page, option choice when there are several, owner checked server-side. |
| P2.7 | Risk register approval in the app | Solved: Approval section on the register (status, summary, approve), on the approver worklist. |
| P2.8 | Check before approving an assessment | Solved: "Before you approve" summary (open questions, findings, risk state, separation of duties); open questions need explicit confirmation. |
| P2.9 | Success messages after saving | Solved for answers ("Answer saved on … It applies to every configuration that uses it"). Correction: product-page actions already showed messages. |
| P3.10 | Slugs derived from names | Solved: add forms ask only for a name; edit forms keep an optional slug. |
| P3.11 | One product overview | Partly: the Organisation page has a breadcrumb, and the portfolio links to organisations. Merging the two pages is deferred. |
| P3.12 | Progress columns on the Portfolio | Solved. |
| P3.13 | Evidence links from controls | Solved for controls on the risk entry page (linked evidence, or a link to add some). Requirement-level evidence links are not shown on the assessment page yet. |

**Found and fixed during the work**

- Assessment pages checked roles at product-family scope only, so roles granted on a single product were ignored there. They now use product scope like the product and risk pages.
- In the first re-run, an empty register's next step pointed back to the register itself; it now opens the add-entry form.
- The Approval step originally ignored the configuration's own approval; it now includes it.

**Still open**

- **HW and SW editors are still one Editor role.** The level badges, filter and shortcuts make clear who should answer what, but nothing restricts it. A scoped role needs a design decision.
- **The questionnaire is long** (88 questions for CRA + RED in the demo), and its total grows as answers make conditional questions apply. The level and open filters help; a per-group progress view could help more.
- **Entity approvals stay one row at a time** (product, variants, revisions, releases, options, configurations); there is no bulk approve.
- **Risk register approval has no separation-of-duties check**, as before in admin.
- **Cost:** the workflow, worklist and portfolio progress are computed per request. Fine at demo scale; watch with larger portfolios.

The original analysis follows unchanged.


`main` at `a4cfd14`, 2026-10-11. Based on a review of every page template and a browser walkthrough with realistic data:

- one product (TempSense: one HW variant and revision, one SW release with an option, one configuration);
- packages `eu-cra`, `eu-red`, two risk methods and a demo risk catalog;
- three users with family-level roles: **edna** (editor), **ana** (approver) and **sam** (editor and approver, the small-organisation case).

## Short answers

| Question | Answer |
| --- | --- |
| Does the UI flow from one task to the next? | **Partly.** The product → configuration → questionnaire → assessment → risk register chain exists. But it is a chain of side links, not a guided flow. The approver has no flow at all, and risk approval is only in Django admin. |
| Does every page have a clear way forward and back to its parent? | **No.** Only the product page has a breadcrumb trail. The questionnaire and assessment pages have no link back to the product. Risk pages link back one level only. The product family in the breadcrumb is not a link. |
| Is the UI intuitive? | **For an editor, mostly; for an approver, no.** Inline editing, tabs and the questionnaire's jump-to-next-open-question work well. The weak points are: the configuration page is really the questionnaire, an 83-question page with "Start new assessment" at the very bottom, results shown as raw ids, and approval actions scattered across rows. |
| Does the UI provide the status information needed? | **For questions, yes; for approval, no.** Questions progress, readiness checklists and risk counts are good. Missing: what is waiting for approval, whether an assessment can be approved (it can be approved with 82/83 questions unanswered), and the risk-assessment status (draft, approved or stale). |

## 1. Page-by-page navigation map

"Back" means a link to the parent level. "Forward" means the next task.

| Page | Back to parent | Forward to next task | Notes |
| --- | --- | --- | --- |
| Dashboard `/` | — | Products, "Continue working on" (editor tasks only) | No task list for approvers: ana sees "Nothing pending" while a product, four entities and an assessment are in draft. |
| Portfolio | — | Product rows, "+ Add product" | No status columns (questions, compliance, risk); those are only on the Compliance page. |
| Organisation `/orgs/<slug>/` | none (not in the nav) | Product links | Reachable only from the product breadcrumb. Its layout differs from Portfolio. |
| Product | Breadcrumb: Portfolio / Acme / *Sensors (not a link)* | Configuration name; small "Risk register" hint link; Evidence | No headings; no per-configuration status (assessment state, progress, risk). |
| Configuration = questionnaire | **None.** The product name is plain text. | "Risk register →" at the top; "Start new assessment" at the bottom of a page about 6,900 px tall | The page title is the configuration name, but the content is the questionnaire. |
| Assessment | **None** to the product; links to the questionnaire and risk register only | "Approve (freezes a snapshot)" for the approver | Results list requirement and route **ids** (`annex_i_2a_...`), not labels. |
| Risk register | "TempSense / TempSense EU 1.0" (good) | "+ Add entry", suggestions | No risk-approval action or status. |
| Risk entry / form / suggestions | "← Risk register" only | Edit / Delete | Two levels up from the product; no link to the product. |
| Evidence list | Product name link | Evidence detail | Not linked from the configuration, assessment or risk pages. |

## 2. Editor perspective (edna, and sam as editor)

**Works well**
- Inline add, edit and clone of HW variants, revisions, SW releases and options keeps the editor on the product page. The selected tab is remembered.
- Saving an answer jumps to the next open question (`#q-<next>`). The "Show only questions still to answer" filter, the question groups and the "Good to understand before you answer" notes make an 83-question form workable.
- An empty risk register explains itself with a readiness checklist ("Target markets set", "A risk method is available", …) that links to the fix.
- The dashboard "Continue working on" list moves from "Start an assessment" to "Complete the assessment" as work progresses.

**Problems**
1. **No way back from the questionnaire or the assessment to the product.** After answering, the editor usually returns to the product (to add a revision or option, or open another configuration). Today that means the browser Back button or Portfolio → product.
2. **The next step after the questionnaire is hidden.** "Start new assessment" is the last element on a very long page. With 82 open questions nothing tells the editor that starting the assessment is the next step. The assessment page then says "82 of 83 still to answer" and sends them back.
3. **Concept overload: configuration vs assessment.** The editor answers questions on the *configuration* page, then creates an *assessment* that only snapshots them. The product page links to the configuration, not to its current assessment, and does not show whether one exists.
4. **No success feedback after saving an answer.** The page reloads and scrolls to the next question; the only signal is the origin badge changing. Product-page actions behave the same way.
5. **The risk register is a side link.** On the product page it is a small hint-styled link under the configuration name; on the questionnaire it is a text link. Nothing presents risk assessment as the step after the questionnaire.
6. **Raw identifiers in results.** Requirements and assessment routes print as ids (`module_a_internal_control`, `art_10_3_conformity_assessment`) although every package defines readable labels.
7. **Slugs are asked for in every "add" form** (product, variant, option). Users should not have to invent slugs; derive them from the name.

## 3. HW editor vs SW editor (your question)

**In the app today they are the same role.** There is a single *Editor* role, granted on an organisation, product family or product. Every editor can answer every question and edit every hardware and software entity of the product. A separate HW editor and SW editor can each be given the editor role, but the system can't tell them apart or restrict either one.

**If they are separate people, it is not clear which questions each should answer.**
- Every question has a level in its package (product, hardware, software or option). In `eu-cra` + `eu-red` + `common` that comes to about 48 product-level, 49 software-level and 12 hardware-level questions.
- **The level is never shown before answering.** It decides where an answer is stored, but it only travels in a hidden form field. The "Origin" column says "unanswered" until someone answers, and only then shows the level.
- The question groups follow the regulation's structure, not ownership, so hardware and software questions are mixed. For example, "Interfaces and exposure" mixes hardware capability questions with software exposure questions.
- There is no filter "show only hardware (or software) questions", and no questionnaire per HW revision or per SW release. A HW editor has to open some configuration and pick out the hardware questions.
- **Side effects are invisible.** An answer to a software-level question is stored on the SW release, so it changes every configuration that uses that release. A hardware answer changes every configuration of that revision. The form doesn't say so.
- **A trap with options:** an option-level answer is stored on the configuration's *first* option. With several options, the editor can't see or choose which one.

**Suggestions for separate HW and SW editors**
- Show each question's level as a badge ("Hardware · rev A", "Software · Firmware 1.0", "Product") next to the answer field, plus a hint "applies to all configurations using …".
- Add a level filter next to "Show only questions still to answer", or tabs (All / Product / Hardware / Software / Options) with open-question counts per tab.
- Add "Questions" entry points on the product page per HW revision and per SW release, showing only that level's questions. That gives each owner their own worklist without choosing a configuration.
- For several options, let the editor choose which option the answer belongs to (or show it per option).
- Optional, later: scope the editor role to hardware or software. That means an extension of role assignments and an ADR. Showing the level and adding a filter cover most of the need without it.

## 4. Approver perspective (ana, and sam as approver)

**Problems**
1. **No approval worklist.** The dashboard tasks are built from editor work only. The approver has to find drafts by opening each product and each tab. Draft badges exist, but nothing summarises "N items waiting for your approval".
2. **Approval is spread over many places.** There are separate Approve buttons on the product header, every HW variant, revision, SW release, option and configuration row (across three tabs), on the assessment page, and for the risk assessment **only in Django admin** (`RiskAssessment` approve action). The risk register has no approval UI or status.
3. **No gate or summary before approving an assessment.** "Approve (freezes a snapshot)" is offered while 82 of 83 questions are unanswered. The warning above it is easy to read past, and there's no confirmation, no summary of findings, and no separation-of-duties hint before clicking.
4. **The order of approvals is not explained.** Product approval says it "does not require any compliance package or risk assessment to be complete". The relationship between entity approval, configuration approval, assessment approval and the risk snapshot is not shown anywhere in the flow.
5. **Stale state is weak.** "(stale)" shows only in the assessment list on the questionnaire page, and as a dashboard task for editors. The product page and Compliance page don't show it.

**Small organisation (sam has both roles)**
- sam sees both edit and approve buttons on every row (Edit, Clone, Approve, Delete). It works, but the rows are crowded.
- The separation-of-duties policy can warn or block self-approval, but the UI says nothing until after the click. A short note next to Approve ("You edited this; your organisation's policy is warn") would avoid surprises.

## 5. Status information

| Status | Shown? | Where |
| --- | --- | --- |
| Questions answered / open / needing confirmation | Yes | Questionnaire, assessment, product, Compliance |
| Compliance and risk ratios | Yes | Dashboard, product, Compliance |
| Draft / approved per entity | Yes | Product tabs (badges) |
| Assessment exists / draft / approved / stale, per configuration | **No** on the product page | Only on the questionnaire page (list at the bottom) |
| What awaits approval | **No** | — |
| Risk assessment status (draft / approved / stale) | **No** in the app | Admin only |
| Readiness (markets, methods, catalogs) | Yes | Empty risk register, assessment without packages |
| Feedback after save | Partly | Risk pages flash "Entry added."; answers and product actions don't |

## 6. Suggested improvements, by priority

**P1: fixes the flow (small changes, high value)**
1. **One breadcrumb component on every page below the portfolio:** Portfolio / Organisation / Family / Product / Configuration / (Assessment | Risk register) / Entry. Add a family page or a family filter on the portfolio, so the family crumb can be a link.
2. **A "Next step" bar** on the questionnaire, assessment and risk register pages. It shows the configuration's workflow as steps (Questions → Assessment → Risk register → Approval) with a status for each and one primary button for the next step. Move "Start new assessment" into it.
3. **Per-configuration status on the product's Configurations tab:** a questions bar, assessment status (none / draft / approved / stale) with a link to it, risk entries and must-treat count, and approval status. Make the Questions and Risk register links equally prominent.
4. **Approver worklist** on the dashboard (and a nav item): drafts waiting for approval, grouped by product, linking to the exact row or page.
5. **Show readable labels** for requirements and routes on the assessment page, grouped by package, with in-force, upcoming and ended sections.

**P2: makes the roles clear**

6. Show each question's level and owner, add a level filter, and add per-revision and per-release question entry points (section 3).
7. **Risk-assessment approval in the app:** "Approve risk register for this configuration" on the register page, with status and stale flag (it exists only in admin today).
8. **An approval check before approving an assessment:** open questions, findings by level, risk status and the separation-of-duties note, with a confirmation step. Optionally block approval while questions are open.
9. Success messages after saving answers and product-page actions.

**P3: polish**

10. Derive slugs from names.
11. Merge the Organisation page into the Portfolio (or add it to the nav), so there is one product overview.
12. Add progress columns to the Portfolio, or merge the Portfolio and the Compliance overview.
13. Link evidence from the controls and requirements that use it, and back.

## Method and limits

- The Playwright walkthrough was run as edna (editor) and ana (approver), against a local server with PostgreSQL. Screenshots and per-page link and button inventories were captured. sam's combined view comes from the templates, which show the union of the editor's and approver's controls.
- Not covered: mobile layout, accessibility audit, evidence workflows in depth, and real users. A short test with 2–3 real HW, SW and approver users on the P1 changes would confirm the priorities.
