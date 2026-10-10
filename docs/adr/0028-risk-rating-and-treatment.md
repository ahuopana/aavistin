# 28. Rating, treatment, controls and deletion in the risk register UI

Status: Accepted

## Context

ADR 0027 added entries by hand; rating, consequences, treatment and controls were still Django-admin-only, so a register could be filled but not scored. The models (ADR 0005) and the scoring (`apps.risk.rating`, `apps.packages.method_engine`) already existed.

## Decisions

- **Small POST-only forms on the entry page**, flash-and-redirect as in ADR 0010, each returning to its section (`#rating`, `#consequences`, `#controls`). No separate pages: every form is one row of fields.
- **Which methods apply.** A threat is rated under each approved method whose `properties` include the threat's violated property. A hazard is rated under each approved method that rates none of confidentiality, integrity or availability (the safety-style methods), or under every approved method if no such method exists. The CIA set is the model's existing `CIAProperty`, not a regulation's content. A rating under a method that no longer applies stays visible so it can be cleared.
- **Scales come from the method package** (`severity`/`likelihood` `scale` and `labels`); values outside the scale are rejected.
- **Consequence severity defaults to the asset's rating** for the violated property (under the first applicable method that has one). Choosing another value marks the consequence as an override, which needs a justification (architecture: "overrides need a justification"). With no asset rating there is nothing to override. Consequences span methods, so they use the first applicable method's severity scale.
- **Clearing a rating removes its treatment**, since a residual rating without a rating means nothing.
- **Treatment justification** is required unless the treatment is *mitigate* and the residual rating is acceptable without one (the method's acceptance is `accept`, or no residual is given yet). Accept, transfer and avoid are decisions to explain, and so is a residual the method marks `justify` or `must_treat`.
- **Controls on threats only, for now.** A control can be created and linked, an existing product control linked, its status changed, or unlinked; a control is never deleted from an entry page because other threats may share it. Linking controls to hazard causes, and editing causes, stay in admin.
- **Deleting an entry** goes through a confirmation page that lists what is deleted with it (ratings, treatments, consequences, causes) and what stays but is unlinked (threats targeting a deleted asset, consequences linking a deleted hazard, controls). An entry with configuration deltas can't be deleted until its deltas are. A deleted catalog suggestion can be suggested again; dismissing suggestions in the app is a later slice.

## Consequences

- An approved risk assessment keeps its snapshot; edits here only make it stale, as before.
- Still admin-only: hazard causes and their controls, deltas, suggestion review, risk assessment approval.
