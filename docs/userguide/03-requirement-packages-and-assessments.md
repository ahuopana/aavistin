# Requirement packages and assessments

## Requirement packages

A **requirement package** encodes one regulation, standard or internal
policy: a set of questions, a scope rule, classifications, requirements,
assessment routes and finding rules. Packages are authored data, not
application code — Aavistin never hard-codes what a regulation requires;
it only knows how to evaluate a package against your answers. See the
[EU CRA package](https://github.com/ahuopana/aavistin/tree/main/packages/eu-cra)
for a real example.

Each package targets a **jurisdiction** (e.g. EU, US). A package is only
active for a configuration if that configuration's hardware revision has
a matching target market. Real, non-demo packages (such as the EU Cyber
Resilience Act) live in the `packages/` directory of the Aavistin
repository, alongside a README noting anything still pending legal
review.

## Answering questions

Each active package's questions are gathered into a single questionnaire
for the configuration. Answers can be recorded at different levels
(product, hardware revision, software release, …) and are resolved down
to the configuration with the most specific answer winning — an answer
at a more specific level can override one inherited from above, with a
justification if the value actually differs.

## What evaluation produces

For each active package, evaluating a configuration works out:

- **In scope or not** — whether the package's scope rule, run against
  your answers, includes or excludes this configuration.
- **Classification(s)** — which of the package's classifications match
  (e.g. "default", "important", "critical" for the EU CRA package).
- **Requirements** — which of the package's requirements apply, given
  the classification(s).
- **Assessment routes** — which conformity routes (e.g. "internal
  control" vs. "third-party assessment") are allowed for this
  classification.
- **Findings** — caution or action-required messages the package's
  rules raise for this specific combination of answers.

## Approval and staleness

Once an assessment's questionnaire is complete, it can be **approved** —
this freezes a snapshot of the evaluation (results, findings, resolved
answers) for audit purposes. If the underlying data changes afterwards
(an answer changes, or the package itself is updated), the approved
assessment is flagged **stale** and due for re-review — it is not
silently recalculated.
