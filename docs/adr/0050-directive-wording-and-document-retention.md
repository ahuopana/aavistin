# 50. Directive wording checked against the Official Journal; document retention question

Status: Accepted (content is not legally reviewed).

## Context

The review of the EMC package (ADR 0049) asked where its wording came from. Several texts had been written from memory and from the Commission guides. Once the Official Journal text of Directive 2014/30/EU was available, it showed differences, and it also showed that the LVD, RED and EMC packages treat two shared topics loosely: the 10-year retention duty was only a sentence in a question's guidance, and the "declaration of conformity" was called that, or the "EU declaration of conformity", in different places.

## Decisions

- **`eu-emc` 1.1.0** (`2014-30@2026-11`, supersedes 1.0.0), changed against the directive text:
  - The "inherently benign" choice becomes `cannot_cause_or_suffer_disturbance`, after Art. 2(2)(d), which has two parts that both must hold. The directive does not use "benign". Choice labels are generated from the ids, so the id carries the wording.
  - Custom-built evaluation kits for professionals (Art. 2(2)(e)) are excluded; they were missing.
  - Marine equipment and medical devices cite Art. 2(3): the directive stops applying where other Union legislation lays down the EMC requirements more specifically. The reading that those acts do so is ours, and is said so in `ref`. Components stay a labelled interpretation of the definition of apparatus (Commission EMC Guide).
  - The use-information question and requirement follow Art. 18: precautions for assembly, installation, maintenance and use, and a clear indication of any restriction of use in residential areas.
  - The importer requirements follow Art. 9(1) to (8). The sample-testing duty that 1.0.0 copied from the LVD is removed, and the Art. 9(4) instructions duty is added.
  - The fixed-installation documentation follows Art. 19(1): the good engineering practices are documented and held at the authorities' disposal while the installation operates. Identifying the person responsible is left to the Member States (Art. 19(3)), so it is no longer an operator duty.
  - Sub-article references (Art. 7(1) to (9), Art. 8(2), Art. 10(1) to (5), Art. 43 for the transition) replace the whole-article ones.
- **`common` 1.5.0** adds `technical_documentation_retention_arranged`: keep the technical documentation and the EU declaration of conformity for 10 years after the product has been placed on the market (LVD Art. 6(3), RED Art. 10(4), EMC Art. 7(3)). All 1.4.0 questions stay. The documentation guidance no longer carries the retention sentence, and the guidance on the EU declaration of conformity, CE marking and product identification follows the directives: one declaration may cover all Union acts (EMC Art. 15(3)), the CE marking goes on the product or its data plate and only where that is not possible or not warranted on the packaging and documents (Art. 17(1)), and the identification may move to the packaging where the size or nature of the product does not allow it (Art. 7(5)).
- **`eu-lvd` 1.2.0** and **`eu-red` 1.2.0** ask the retention question, with an action-required finding for a "no", and say "EU declaration of conformity" throughout. `eu-emc` 1.1.0 does the same.
- **One term: "EU declaration of conformity"**, as the directives write it, in lowercase after the first word. Neither "DoC" nor "EU DoC" appears in package text. Whether the user combines it with declarations for other markets is theirs to decide, and the guidance says so.
- **The duplicate findings between `eu-lvd` and `eu-emc` stay accepted** (ADR 0049); the retention finding is one more of them.

## Consequences

- Approving the new versions supersedes the old ones, so approved assessments become stale as for any package version change. Old versions stay in the repository.
- `eu-cra` still says "declaration of conformity" in two requirement labels. It is left as it is, because a version bump for wording alone would make every approved CRA assessment stale. It can ride the next functional CRA version.
- Only the references that this change touches were checked against the Official Journal. The older LVD and RED references have not been audited.
- Not done: the second conformity route (EU type examination, Annex III) and a type for apparatus made only for one particular fixed installation are listed as limitations in the `eu-emc` README.
- Legal review: the requirement summaries, the Art. 2(3) readings for marine equipment and medical devices, and the component exclusion.
