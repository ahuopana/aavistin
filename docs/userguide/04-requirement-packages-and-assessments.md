# Requirement packages and assessments

## Requirement packages

A **requirement package** encodes one regulation, standard or internal
policy: a set of questions, a scope rule, classifications, requirements,
assessment routes and finding rules. Packages are authored data, not
application code — Aavistin never hard-codes what a regulation requires;
it only knows how to evaluate a package against your answers. See the
[EU CRA package](https://github.com/ahuopana/aavistin/tree/main/packages/eu-cra)
and the
[EU Low Voltage Directive package](https://github.com/ahuopana/aavistin/tree/main/packages/eu-lvd)
for real examples. The
[EU EMC Directive package](https://github.com/ahuopana/aavistin/tree/main/packages/eu-emc)
works the same way; a mains-powered product without a radio is in both, and a
missing declaration of conformity or CE marking then shows as a finding under each.

Each package targets a **jurisdiction** (e.g. EU, US). A package is only
active for a configuration if that configuration's target markets include
it (the hardware variant's and the software release's markets, see
[organisations and products](organisations-and-products)). Real, non-demo
packages (such as the EU Cyber Resilience Act and the Low Voltage
Directive) live in the `packages/`
directory of the Aavistin repository, alongside a README noting anything
still pending legal review.

## Answering questions

Each active package's questions are gathered into a single questionnaire
for the configuration. Answers can be recorded at different levels
(product, hardware revision, software release, …) and are resolved down
to the configuration with the most specific answer winning — an answer
at a more specific level can override one inherited from above, with a
justification if the value actually differs.

Each question shows the level it is answered at, and where the answer is
stored, e.g. "Hardware · EU variant rev A" or "Software · Firmware 1.0".
The answer applies to every configuration that uses that revision,
release or option. Use the **Answered at** filter to see only one level:
a hardware engineer can work through the hardware questions and a
software engineer through the software ones. The product page also links
straight to them from each hardware revision ("Hardware questions"),
software release and option. When a configuration has several options,
an option-level question lets you pick which option the answer belongs
to.

### Questionnaire progress

The top of the questionnaire shows how far it has got: how many active
questions are answered, and how many are still to answer — split into
**unanswered** (no value yet) and **needs confirmation** (carried forward
from a previous software release and not yet confirmed). Questions filled
in automatically from other answers count as answered and are shown as
**derived**. Tick *Show only questions still to answer* to hide the
finished ones; the filter is kept in the link (`?show=open`), so it can
be shared. Answering a question can make further questions apply, so
the total may grow as you go.

A draft assessment repeats the count with a link straight to the open
questions. The same progress, summed over a product's configurations,
appears as the **Questions** bar on the product page and on the
Compliance Overview.

## What evaluation produces

For each active package, evaluating a configuration works out:

- **In scope or not** — whether the package's scope rule, run against
  your answers, includes or excludes this configuration.
- **Classification(s)** — which of the package's classifications match
  (e.g. "default", "important class I", "critical" for the EU CRA package).
- **Your role** — manufacturer, importer, distributor, authorised
  representative or open-source steward, where the package asks for it.
  Only that role's requirements are listed; while unanswered, all are.
- **Requirements** — which of the package's requirements apply, given
  the classification(s), your role and your answers (e.g. when the product
  was placed on the market). Requirements with a start date that hasn't
  passed yet are listed separately as "not in force yet", and those whose
  end date has passed as "no longer in force".
- **Assessment routes** — which conformity routes (e.g. "internal
  control" vs. "third-party assessment") are allowed for this
  classification.
- **Findings** — caution or action-required messages the package's
  rules raise for this specific combination of answers.

## Acting on findings

The assessment page lists findings most severe first. Each one names the
package and legal reference that raised it, and **Based on** lists the
answers that triggered it, each linked to its question. Where the package
author has written it, **What to do** says how to resolve the finding.

- **Action required**: something the regulation requires is missing or
  needs a specific procedure (e.g. a notified body, an SBOM, a
  vulnerability reporting process). Fix it in the product or in your
  processes, then update the answers it is based on. The finding goes
  away once the answers no longer trigger it. If an answer was simply
  wrong, correct it. Until then, the finding counts against the
  **Compliance** ratio. An assessment can still be approved with open
  findings; the snapshot records them.
- **Caution**: not a gap yet, but a point to check or decide on, such as
  a disabled radio that an update could enable. Decide whether it applies
  to you and record the decision, for example as a risk register entry.
  Cautions don't affect the Compliance ratio.
- **Info**: background only; nothing to do.

A finding marked **package not in scope** comes from a regulation that
doesn't apply to the configuration with the current answers. It doesn't
count against compliance, but becomes relevant if the scope changes.

## The Compliance ratio

The **Compliance** bar on the dashboard, the portfolio, the product page
and the Compliance Overview counts the requirements in force for the
product's configurations, based on their current answers. A requirement
counts as fulfilled unless its package has an action-required finding for
that configuration. Findings belong to a package as a whole, not to
individual requirements, so one finding stops all of that package's
requirements from counting. A requirement that is in force for several
configurations is counted once.

Click a product's ratio, or hover over the **?** for a short explanation,
to open its **compliance breakdown**. It lists, per configuration and
package, the requirements counted and the findings that block them; each
finding links to its entry on the assessment page. The Compliance
Overview also shows the number of open action-required findings per
product.

When there is nothing to count, the bar says why:

- **Not in scope**: the product's configurations were assessed against the
  active packages and none of them applies with the current answers (for
  example, a product excluded from the CRA and the RED). If questions are
  still open, the scope may change once they are answered.
- **None in force yet**: a package applies, but none of its requirements
  is in force yet (for example, most EU CRA requirements apply from
  11 December 2027).
- **No data yet**: there is no configuration, or no package is approved
  for the configurations' target markets.

The breakdown shows the same reason for each configuration.

## Approval and staleness

Once an assessment's questionnaire is complete, it can be **approved** —
this freezes a snapshot of the evaluation (results, findings, resolved
answers) for audit purposes. If the underlying data changes afterwards
(an answer changes, the package itself is updated, or a date passes that
brings a requirement into force or ends it), the approved assessment is
flagged **stale** and due for re-review — it is not silently recalculated.

Before approving, the assessment page shows a **Before you approve**
summary: open questions, findings by level, the risk register's state
and, if you edited answers yourself, what the separation-of-duties
policy says. Approving with questions still open needs an explicit
confirmation.

## EU Cyber Resilience Act

The EU CRA package asks for the product's core functionality as one choice
from the categories of Annexes III and IV of the regulation. The category
names are quoted from Regulation (EU) 2024/2847 of the European Parliament
and of the Council (Cyber Resilience Act), OJ L, 2024/2847, 20.11.2024,
ELI: http://data.europa.eu/eli/reg/2024/2847/oj. Source: EUR-Lex,
© European Union, 1998–2026; reuse authorised with acknowledgement of the
source. Only the published Official Journal text is authentic.

The "Good to understand before you answer" notes are our own summaries of
the Commission's guidance on the application of the CRA, C(2026) 5252,
not the guidance itself. The package is not legal advice and is pending
legal review; see the package README.

## EU Radio Equipment Directive

The EU RED package applies to products with a radio that can be used. It
asks whether the radio is enabled per software release and option, so an
option that switches the radio off or on shows why the scope changes. The
network protection, privacy and fraud requirements of Delegated Regulation
(EU) 2022/30 are derived from what the product does (internet connection,
personal data, money transfer, toys, childcare and wearables), and apply
only to units placed on the market from 1 August 2025.

For general EU product rules (placing on the market, the roles of
manufacturers, importers and distributors, harmonised standards,
conformity assessment and CE marking), the package links to the
Commission's [Blue Guide on the implementation of EU product rules
2022](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=oj%3AJOC_2022_247_R_0001).
The "Good to understand before you answer" notes are our own summaries.
The package is not legal advice and is pending legal review; see the
package README.
