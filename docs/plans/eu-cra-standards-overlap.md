# Research: questions shared by the EU CRA, IEC 62443 and NIST SSDF

Status: research input to `docs/plans/eu-cra-full.md`, not a decision. Requirement ids marked † are unverified (from memory); check them against the standards or the ENISA/JRC mapping before relying on them.

**Verification status.** WebSearch worked, but WebFetch was blocked by the egress proxy for every domain tried: csrc.nist.gov, enisa.europa.eu, myctrl.tools, edu.chainguard.dev, jtsec.es and cycode.com. So no primary document (SP 800-218, the ENISA/JRC mapping PDF, the CISA form) could be read in full. Only search-result snippets and summaries could be checked. Requirement ids confirmed that way are listed in section 5. **All other requirement ids and every confidence rating below are unverified (from memory)** and are marked with a dagger (†) at first use in each table. Before relying on any id, check it against the standard or the ENISA/JRC PDF.

**Copyright.** IEC 62443 requirements appear only as part + id with our own short summaries; no requirement titles or text are reproduced. SSDF appears as practice/task ids with own summaries. CRA is paraphrased with article/annex refs.

Abbreviations: **4-1** = IEC 62443-4-1:2018 (secure product development lifecycle), **4-2** = IEC 62443-4-2:2019 (technical requirements for components), **3-3** = IEC 62443-3-3 (system requirements), **SSDF** = NIST SP 800-218 v1.1, **CISA** = CISA Secure Software Development Attestation Form (2024). CR = component requirement; EDR/HDR/NDR/SAR = embedded-device, host-device, network-device and software-application specific requirements.

---

## 0. Key findings

1. **The overlap splits cleanly in two.** Facts about the manufacturer's *process* overlap across all three specs: SDL, threat modelling, third-party components, SBOM, testing, CVD, remediation, advisories, release signing. Facts about the *product's properties* overlap only between CRA Annex I Part I and 62443-4-2, because SSDF is process-only. Its only product-facing tasks are PW.9 (secure defaults), PS.2 (integrity verification of releases) and, weakly, PW.1.3 (use standard security features).
2. **The current schema has no level for process facts.** Levels are `product | hardware | software | option`, and answers attach to Product / HardwareRevision / SoftwareRelease / SoftwareOption (ADR 0004). An organisation-wide SDL has to be answered per product. The recommendation is `product` level for policies and `software` level for per-release activities, plus an ADR follow-up for organisation- or family-level answers (section 4.1).
3. **`choice` is single-valued and comparisons are number-only.** `apps/packages/ruleengine.py` `_comparison` rejects non-numbers, and the linter raises `type_mismatch` for a non-number under a numeric op. So ordinal facts such as 62443 security level must be `number`, not `choice`. Multi-select facts, such as which interfaces exist, must be split into several questions.
4. **Some proposed ids would clash with existing ones.** The demo package declares `has_wireless` (boolean, hardware). The capability-versus-enablement modelling in `docs/architecture.md` suggests a `choice` instead. Use a new id (`wireless_interface_capability`) rather than reuse `has_wireless` with a different type, which the linter rejects (ADR 0015).

---

## 1. Candidate shared questions

Columns: **Use** = how each spec uses the fact. S = scope/applicability, C = classification/profile selection, R = trigger for a requirement, F = trigger for a finding. "—" = the spec does not use the fact. Ids follow the existing `packages/common` style (snake_case, `uses_` / `has_` / `mfa_for_` prefixes, booleans phrased as facts).

### 1a. Product facts (properties of the product)

| # | Proposed id | Type | Level | Label (own words) | CRA | IEC 62443 | SSDF | `implied_by` candidate |
|---|---|---|---|---|---|---|---|---|
| P1 | `has_data_connection` | boolean | software | Can the product exchange data with another device or network, directly or indirectly, including through remote data processing? | S: Art. 2(1), Art. 3(1)-(2) definition of product with digital elements | C: whether network-facing CRs/NDRs apply (4-2 FR5†) | — (SSDF applies to all software) | Yes: true when `network_interface_capability == "present"` or `wireless_interface_capability == "present"`. Never derive *false*. |
| P2 | `network_interface_capability` | choice: `not_present`, `present`, `present_physically_disabled` | hardware | Does the hardware have a wired data interface (Ethernet, fieldbus, USB data, serial)? | S, F: Annex I Part I(2)(j) attack surface; caution finding when disabled but present | R: 4-2 CR 5.1† (segmentation support), CR 7.7† | — | No |
| P3 | `wireless_interface_capability` | choice: same as P2 | hardware | Does the hardware have a radio (Wi-Fi, Bluetooth, cellular, LoRa…)? | S, F: Part I(2)(j); shared with RED | R: 4-2 CR 2.2† (wireless use control), CR 1.6† (wireless access management) | — | No. Supersedes demo `has_wireless` (see 4.6) |
| P4 | `network_services_exposure` | choice: `none`, `outbound_only`, `listening_enabled_by_default`, `listening_disabled_by_default` | software | Does the software accept inbound connections (listening ports, APIs, remote admin), and are they on out of the box? | R/F: Part I(2)(b), (2)(j) | R: 4-2 CR 7.7† (least functionality); 4-1 SG-3† (hardening guidance) | R: PW.9.1† (secure default settings) | Could imply P1 (`!= "none"` ⇒ data connection) |
| P5 | `physical_debug_interface` | choice: `none`, `present_open`, `present_access_controlled`, `disabled_in_production` | hardware | Does the hardware expose debug/test ports (JTAG, SWD, UART console)? How are they protected in shipped units? | F: Part I(2)(d), (2)(j) | R: 4-2 EDR/HDR/NDR 2.13† (physical diagnostic/test interfaces) | — | No |
| P6 | `requires_user_authentication` | boolean | software | Must a person or system authenticate before using or configuring the product? | R/F: Part I(2)(d) | R: 4-2 CR 1.1 (human users), CR 1.2 (software processes/devices) | weak: PW.1.3† | Yes: true if `uses_mfa` is true |
| P7 | `default_credentials` | choice: `none`, `unique_per_unit`, `set_by_user_at_first_use`, `shared_default` | software | How are initial credentials provided? `shared_default` = same password on every unit. | F (action required on `shared_default`): Part I(2)(b), (2)(d) | R: 4-2 CR 1.5† (authenticator management incl. changing initial values), CR 1.7 (password strength) | R: PW.9.1† | Condition: `requires_user_authentication` |
| P8 | `uses_mfa` *(exists)* | boolean | software | Does the product support multi-factor authentication? | R: Part I(2)(d) (not mandated, a means) | R: 4-2 CR 1.1 requirement enhancements† (MFA by network trust, at higher SL) | — | **Propose:** true when `mfa_for_admin_access` or `mfa_for_all_users` is true (no cycle with the existing rule) |
| P9 | `mfa_for_admin_access` *(exists)* | boolean | software | MFA required for administrative access? | as P8 | as P8 | — | Exists: ⇐ `mfa_for_all_users` |
| P10 | `mfa_for_all_users` *(exists)* | boolean | software | MFA required for all users? | as P8 | as P8 | — | — |
| P11 | `role_based_access_control` | boolean | software | Can access rights be restricted per role or user, with least privilege? | R: Part I(2)(d) | R: 4-2 CR 2.1† (authorisation enforcement), CR 1.3† (account management) | — | No |
| P12 | `encrypts_data_in_transit` | choice: `all_external_channels`, `some_channels`, `none` | software | Is data sent over external interfaces protected (encryption and integrity, e.g. TLS)? | R/F: Part I(2)(e), (2)(f) | R: 4-2 CR 3.1† (communication integrity), CR 4.1† (information confidentiality), CR 4.3† (use of cryptography) | weak: PW.1.3† | Condition: `has_data_connection` |
| P13 | `sensitive_data_at_rest` | choice: `none_stored`, `stored_encrypted`, `stored_unencrypted` | software | Does the product store secrets, credentials or personal/confidential data, and is it encrypted at rest? | R/F: Part I(2)(e) | R: 4-2 CR 4.1†, CR 4.3† | — | No |
| P14 | `update_mechanism` | choice: `none`, `manual`, `automatic_default_on`, `automatic_default_off` | software | How does the product receive software updates? | R/F: Part I(2)(c) (auto-update on by default, with opt-out); Part II(7), (8) | R: 4-2 EDR/HDR/NDR 3.10† (support for updates); 4-1 SUM-4† (update delivery) | weak: PS.2.1† | No |
| P15 | `verifies_update_authenticity` | boolean | software | Does the product check an update's signature or integrity before installing it? | R: Part I(2)(f); Part II(7) | R: 4-2 EDR/HDR/NDR 3.10 enhancement†, CR 3.4 (software and information integrity); 4-1 SUM-4† | R: PS.2.1† | Condition: `update_mechanism != "none"` |
| P16 | `verifies_boot_integrity` | boolean | hardware | Does the device check its firmware/software against a root of trust at boot (secure boot)? | R: Part I(2)(f), (2)(k) | R: 4-2 EDR/HDR/NDR 3.14† (boot process integrity); EDR 3.12† (supplier roots of trust) | — | No (see 4.4 on level) |
| P17 | `minimal_default_configuration` | boolean | software | In the shipped configuration, are non-essential services, ports, accounts and features off? | R/F: Part I(2)(b), (2)(j) | R: 4-2 CR 7.7†, CR 7.6† (network/security configuration settings); 4-1 SG-3† | R: PW.9.1†, PW.9.2† | No. Do not derive from P4. |
| P18 | `supports_factory_reset` | boolean | software | Can the user restore the original secure state and securely wipe all data and settings? | R: Part I(2)(b) (reset), (2)(m) (removal) | R: 4-2 CR 4.2† (information persistence/purge); 4-1 SG-4† (secure disposal guidance) | — | No |
| P19 | `security_event_logging` | boolean | software | Does the product record security-relevant events (logins, configuration changes, failures) for monitoring? | R: Part I(2)(l) (with user opt-out); (2)(d) reporting unauthorised access | R: 4-2 CR 2.8 (auditable events), CR 2.9†, CR 2.11†, CR 3.9†, CR 6.1† | — (PO.5 logging covers the dev environment, not the product) | No |
| P20 | `dos_resilience_measures` | boolean | software | Are essential functions designed to keep working under flooding or resource exhaustion (rate limits, quotas, degraded mode)? | R: Part I(2)(h), (2)(i) | R: 4-2 CR 7.1† (DoS protection), CR 7.2† (resource management) | — | No |
| P21 | `includes_third_party_components` | boolean | software | Does the software include third-party or open-source components (libraries, OS, firmware blobs)? | R: Art. 13(5)† due diligence; Part II(1) | R: 4-1 SM-9, SM-10, SUM-3 | R: PO.1.3†, PW.4.1†, PW.4.4 | No (nearly always true; consider default guidance) |

### 1b. Process facts (the manufacturer's development and vulnerability handling)

Level: `product` for standing policies, `software` for activities evidenced per release. See section 4.1.

| # | Proposed id | Type | Level | Label (own words) | CRA | IEC 62443 | SSDF / CISA | `implied_by` candidate |
|---|---|---|---|---|---|---|---|---|
| M1 | `documented_secure_development_process` | boolean | product | Is the product developed under a documented secure development lifecycle that is actually followed? | R: Art. 13(1)†; Annex I Part I(1); Annex VII† (tech. docs) | R: 4-1 SM-1 (whole SM practice) | R: PO.1–PO.5† (Prepare the Organization) | No |
| M2 | `security_roles_and_training` | boolean | product | Are security responsibilities assigned, and do developers get role-appropriate security training? | — (implicit in Art. 13(1)) | R: 4-1 SM-2†, SM-4† | R: PO.2.1†, PO.2.2† | No |
| M3 | `performs_cybersecurity_risk_assessment` | boolean | product | Is a documented cybersecurity risk assessment for this product maintained and updated over its lifecycle? | R: Art. 13(2)–(3)†; Annex VII† | R: 4-1 SR-1 (security context), SR-2 (threat model); 3-2† for systems | R: PW.1.1 (risk modelling) | Not from M4 (see 4.3). Could later be derived from the Aavistin risk register; that needs a non-question input. |
| M4 | `performs_threat_modelling` | boolean | product | Is there a threat model for the product, reviewed when the design changes? | weak R: Art. 13(2)† (input to risk assessment) | R: 4-1 SR-2 | R: PW.1.1 | No |
| M5 | `security_requirements_documented` | boolean | product | Are product security requirements written down and traced to design and tests? | weak: Annex VII† | R: 4-1 SR-3†, SR-4†, SR-5† | R: PO.1.2, PW.1.2 | No |
| M6 | `security_design_review` | boolean | software | Is the design reviewed against security requirements and threats before release? | weak: Part I(1) | R: 4-1 SD-1, SD-3†, SD-4 | R: PW.2.1† | No |
| M7 | `secure_coding_standard` | boolean | product | Do developers follow a documented secure coding standard? | weak: Part I(1), (2)(k) | R: 4-1 SI-2† | R: PW.5.1† | No |
| M8 | `code_review_or_static_analysis` | boolean | software | Is code reviewed for security, by people and/or static analysis, before release? | R: Part II(3) | R: 4-1 SI-1† | R: PW.7.1†, PW.7.2† | No |
| M9 | `scans_for_known_vulnerabilities` | boolean | software | Is each release, including its dependencies, scanned for known vulnerabilities (e.g. SCA against CVE data) before release? | R: Part I(2)(a); Part II(1), (3) | R: 4-1 SVV-3, SM-9 | R: PW.4.4, RV.1.1, RV.1.2†; CISA (automated vulnerability checks) | No |
| M10 | `security_testing_before_release` | boolean | software | Is security testing done before each release (security-function tests, fuzzing, dynamic tests)? | R: Part II(3) | R: 4-1 SVV-1, SVV-2†, SVV-3 | R: PW.8.1†, PW.8.2† | **Yes:** ⇐ `penetration_testing_performed` |
| M11 | `penetration_testing_performed` | boolean | software | Was the release penetration-tested? | R: Part II(3) | R: 4-1 SVV-4; SVV-5† (tester independence) | R: PW.8.2† | No |
| M12 | `blocks_release_with_known_exploitable_vulnerabilities` | boolean | product | Is there a policy that a release with known exploitable vulnerabilities is not shipped unless they are fixed or mitigated? | R/F: Part I(2)(a) | R: 4-1 DM-4, SVV-3 | R: RV.2.2; CISA (vulnerabilities addressed before release) | No |
| M13 | `third_party_component_due_diligence` | boolean | product | Are third-party components vetted before use (provenance, maintenance status, known vulns) and monitored afterwards? | R: Art. 13(5)† | R: 4-1 SM-9, SM-10 | R: PO.1.3†, PW.4.1†, PW.4.4; CISA (trusted source code supply chain) | Condition: `includes_third_party_components` |
| M14 | `sbom_scope` | choice: `none`, `top_level_dependencies`, `full_transitive` | software | Is a machine-readable SBOM produced for each release, and how deep does it go? | R/F: Part II(1) (at least top-level); Annex VII† | weak: none explicit in 4-1 ed. 1; SM-9/SUM-3 track components (see 4.2) | R: PS.3.2 (provenance/SBOM); CISA (provenance) | No |
| M15 | `protects_development_environment` | boolean | product | Are source code, build systems and developer endpoints access-controlled, separated and logged? | weak: Part I(1) | R: 4-1 SM-7† (dev environment), SM-6† (file integrity) | R: PO.5.1†, PO.5.2†, PS.1.1†; CISA (secure build environments) | No |
| M16 | `signs_releases` | boolean | product | Are releases and updates signed, with keys kept protected, so recipients can verify them? | R: Part II(7) | R: 4-1 SM-6†, SM-8† (private key control), SUM-4† | R: PS.2.1† | **Yes:** ⇐ `verifies_update_authenticity` (a device that checks signatures implies signed releases) |
| M17 | `monitors_component_vulnerabilities` | boolean | product | After release, are new vulnerabilities in the product and its components monitored (feeds, advisories)? | R: Part II(1)–(2); Art. 13(6)† | R: 4-1 DM-1, SUM-3 | R: RV.1.1 | No |
| M18 | `has_cvd_policy` | boolean | product | Is there a published coordinated vulnerability disclosure policy? | R: Part II(5) | R: 4-1 DM-1, DM-5 | R: RV.1.3; CISA (vulnerability disclosure programme) | No |
| M19 | `has_vulnerability_contact` | boolean | product | Is there a public contact point for reporting vulnerabilities (e.g. security.txt, PSIRT address)? | R: Part II(6); Annex II† | R: 4-1 DM-1 | R: RV.1.3 | Possible: ⇐ `has_cvd_policy` (a CVD policy normally names the channel). Medium confidence; can be left out. |
| M20 | `vulnerability_remediation_process` | boolean | product | Is there a documented process to triage, prioritise and fix reported vulnerabilities, with target times? | R: Part II(2) | R: 4-1 DM-2†, DM-3†, DM-4, SUM-5† | R: RV.2.1†, RV.2.2 | No |
| M21 | `publishes_security_advisories` | boolean | product | Are fixed vulnerabilities published as advisories (description, affected versions, fix)? | R: Part II(4), (8) | R: 4-1 DM-5, SUM-2†, SUM-3 | R: RV.2.2 | No |
| M22 | `provides_secure_use_documentation` | boolean | product | Do users get documentation on secure installation, hardening, operation, updates and decommissioning? | R: Annex II†; Part I(2)(b), (2)(m) | R: 4-1 SG-1† … SG-6† | R: PW.9.2† | No |

**Strongest three-way overlap (high confidence that all three specs care):** M1, M3/M4, M9, M10/M11, M12, M13, M14, M16, M17, M18, M20, M21. Among the product facts, P7, P15 and P17 are the only ones all three specs touch, through SSDF PS.2/PW.9.

**Two-way only, but still worth sharing:** P2–P6 and P11–P20 (CRA + 62443-4-2; also RED/EN 18031 later). M2 and M5–M8 (62443-4-1 + SSDF; CRA only implicitly).

---

## 2. Requirement crosswalk (for evidence reuse)

Confidence rates how well the cited ids cover the CRA item, not whether the ids are verified. Ids marked † could not be confirmed online. The ENISA/JRC report has the authoritative mapping; it could not be fetched.

| CRA item (own summary) | IEC 62443-4-1 | IEC 62443-4-2 | SSDF v1.1 | Confidence | Notes |
|---|---|---|---|---|---|
| I.1 cybersecurity appropriate to risk | SM-1, SR-1, SR-2, SR-3†, SD-1, SD-2†, SD-4 | whole part, via SL-C selection | PO.1.2, PW.1.1, PW.1.2 | medium | 62443 risk-to-requirement link runs through security levels; CRA has none |
| I.2(a) no known exploitable vulns at release | SVV-3, DM-4, SM-9, SUM-3 | — | PW.4.4, PW.7.2†, PW.8.2†, RV.1.1, RV.1.2† | high | Process coverage good; CRA states an outcome, not only a process |
| I.2(b) secure by default, reset to original state | SG-3†, SD-4 | CR 7.6†, CR 7.7†, CR 1.5†, CR 4.2† | PW.9.1†, PW.9.2† | medium (defaults) / low (reset) | No clear 62443 equivalent for "reset to original state" |
| I.2(c) security updates; automatic, default-on, opt-out | SUM-1, SUM-2†, SUM-4†, SUM-5† | EDR/HDR/NDR 3.10† | PS.2.1†, RV.2.2 | medium / low (auto-update) | OT practice is operator-controlled patching; default-on auto-update has no 62443 equivalent |
| I.2(d) protection from unauthorised access; report it | SD-1 | FR1: CR 1.1, 1.2, 1.3†–1.14†; FR2: CR 2.1†, 2.5†–2.7†; CR 2.8, CR 6.2† | PW.1.3† (weak) | high (4-2) / low (SSDF) | "Report possible unauthorised access" ≈ audit + continuous monitoring |
| I.2(e) confidentiality (stored, transmitted, processed) | — | CR 4.1†, CR 4.3†, CR 3.1† | — | high | |
| I.2(f) integrity of data, commands, software, configuration; report corruption | SM-6† | CR 3.1†, CR 3.4, CR 3.8†, 3.10 enh.†, EDR/HDR/NDR 3.14† | PS.2.1† | high (4-2) | "Report corruption" ≈ CR 3.4 enhancement† (automated notification) |
| I.2(g) data minimisation | — | — | — | gap | GDPR overlap, not 62443/SSDF |
| I.2(h) availability, DoS resilience | — | CR 7.1†, CR 7.2†, CR 7.3†, CR 7.4† | — | high (DoS) / medium | |
| I.2(i) limit impact on other devices/networks | — | CR 7.1 enh.†, CR 5.1† | — | low | 3-3 zones/conduits are a system concern |
| I.2(j) limit attack surface | SD-4, SG-3† | CR 7.7†, EDR/HDR/NDR 2.13†, CR 2.2† | PW.9.1† | medium–high | |
| I.2(k) exploitation mitigation | SD-2†, SD-4, SI-2† | CR 3.2† (malicious code), 3.14† | PW.5.1†, PW.6.1†, PW.6.2† (compiler/build hardening) | medium | |
| I.2(l) security logging/monitoring, user opt-out | — | CR 2.8, 2.9†, 2.10†, 2.11†, 3.9†, 6.1†, 6.2† | — | high (logging) / gap (opt-out) | |
| I.2(m) secure data removal and transfer | SG-4† | CR 4.2†; CR 7.3†/7.4† (backup/restore) | — | medium (removal) / low (transfer) | |
| II.1 identify components, SBOM | SM-9, SM-10, SUM-3, DM-1 | CR 7.8† (component inventory: a runtime feature, not an SBOM) | PS.3.2, PO.1.3†, PW.4.1†, PW.4.4 | high (SSDF) / low (62443) | 4-1 ed. 1 has no explicit SBOM; the CRA amendment EN IEC 62443-4-1/A11 is expected to address alignment |
| II.2 remediate without delay; security fixes separate from features | DM-2†, DM-3†, DM-4, SUM-1, SUM-5† | — | RV.2.1†, RV.2.2 | high (remediation) / gap (separation) | |
| II.3 regular security tests and reviews | SVV-1, SVV-2†, SVV-3, SVV-4, SVV-5†, SI-1†, DM-6† | — | PW.7†, PW.8†, RV.1.2† | high | |
| II.4 publicly disclose fixed vulns | DM-5, SUM-2† | — | RV.2.2 | medium | CRA allows delay; timing differs |
| II.5 CVD policy | DM-1, DM-5 | — | RV.1.3 | high | ISO/IEC 29147 is the closest standard |
| II.6 contact point for reports | DM-1 | — | RV.1.3 | high | |
| II.7 secure update distribution | SUM-4†, SM-6†, SM-8† | 3.10 enh.† | PS.2.1†, PS.3.1† | high | |
| II.8 timely, free updates with advisories | SUM-2†, SUM-5†, DM-5 | — | RV.2.2 | medium / gap (free of charge) | |
| Art. 13(2)–(3)† risk assessment | SR-1, SR-2 (3-2† for systems) | — | PW.1.1 | high | Meaning differs (see 4.3) |
| Art. 13(5)† third-party due diligence | SM-9, SM-10 | — | PO.1.3†, PW.4.1†, PW.4.4 | high | |
| Art. 13(8)† support period ≥5 years | (product end-of-life is in 4-1's lifecycle scope; no id recalled with confidence) | — | — | low / gap | |
| Annex VII† technical documentation | SM-1, SR-5†, SG-7† | — | PO.1†, PW.1.2 | low | |
| Annex II† information to users | SG-1† … SG-6† | — | PW.9.2† | medium | |
| Art. 14 reporting (24 h / 72 h / final) | — | — | — | gap | CRA-only; applies from 11 Sep 2026 (verified) |

---

## 3. Spec-specific facts that do not map

### IEC 62443
- **Target security level (SL-C 1–4).** Use `number` (unit `"SL"`, 1–4), not `choice`: rules need `>=`, and the rule engine only compares numbers. 62443 sets a level per foundational requirement (FR1–FR7), so either use one `iec62443_target_sl` number or seven `iec62443_sl_fr1` … `_fr7` numbers. Start with one number plus optional per-FR overrides. Keep these in the 62443 package, not in common.
- **Component type** (SAR / EDR / HDR / NDR). A product can contain several types, and `choice` is single-valued. Use four booleans (`iec62443_is_software_application`, `…_embedded_device`, `…_host_device`, `…_network_device`), or model each type as a HW variant / SW option. 62443-specific.
- **4-1 maturity level** (ML 1–4, process capability): `number`, product level. Specific to 62443.
- **Zones and conduits, 3-2 risk assessment, 3-3 SRs:** system-integrator / asset-owner facts, not product facts. Out of scope for a product questionnaire unless Aavistin models systems. Closest product-side fact: 4-1 SG-2† (countermeasures the product expects from its environment). That could be a 62443-only boolean, `relies_on_environment_countermeasures`.
- **Requirement enhancements (RE) by SL:** derived from the SL number, no extra question.
- **Process/product certification** (e.g. ISASecure SDLA/CSA, IECEE): evidence, not a question.

### NIST SSDF / CISA attestation
- **`supplies_us_federal_government`** (boolean, product): triggers the attestation. US procurement policy, not legislation. Model as a customer-requirement source.
- **Attestation scope:** software developed or majorly changed after the policy cut-off; exemptions for agency-developed software and freely obtained FOSS. Details not verified; from memory.
- **Plan of action and milestones** when a practice cannot be attested; signatory (CEO or designee); third-party assessment option. Unverified.
- **SSDF 1.2** (SP 800-218 Rev. 1, initial public draft, 17 Dec 2025; comments closed 30 Jan 2026; verified that it exists). Task ids may change. Pin the package to v1.1 now and plan a 1.2 package version.

### CRA
- **Support period:** `security_support_period_years` (number, unit `"years"`, product). Rule: finding when < 5 unless expected use time is shorter (needs a second number, `expected_use_time_years`). Annex II† (user information on end date).
- **Reporting (Art. 14):** whether a reporting process exists and is registered with the Single Reporting Platform. CRA-only; applies from 11 Sep 2026, before the main application date. `eu-cra-partial` models only one application date (ADR 0012), so the full package needs phased dates.
- **Automatic updates default-on with opt-out; logging opt-out; free security updates; security updates separate from feature updates:** CRA-only refinements. Ask them in `eu-cra` with a `condition` on the common question (e.g. `update_mechanism`).
- **Data minimisation (I.2(g)) and `processes_personal_data`:** shared with GDPR, not with 62443/SSDF. Still a good common-library candidate.
- **Scope exclusions** (`is_medical_device`, `is_in_vitro_diagnostic`, `is_type_approved_vehicle_component`, `is_civil_aviation_product`, `is_marine_equipment`, `is_national_security_or_defence_only`, `is_identical_spare_part`): CRA-only among the three, but RED, MDR and LVD packages will reuse them. Put them in common.
- **FOSS / commercial activity** (`is_free_and_open_source`, `is_commercial_activity`, now in `eu-cra-partial`): CRA-specific. The CISA form also exempts freely obtained FOSS (unverified), so moving them to common is reasonable.
- **Economic operator role** (manufacturer / importer / distributor / open-source steward): `choice`, product level. Shared with every EU New Legislative Framework package.
- **Annex III/IV classification:** stays CRA-specific (`is_annex_iii_important_product` etc.).
- **Remote data processing** (`uses_remote_data_processing`): affects CRA scope (Art. 3(2)†); not used by 62443 or SSDF.

---

## 4. Modelling notes and pitfalls

### 4.1 Process facts have no natural level
`level` is `product | hardware | software | option`. An SDL, CVD policy or PSIRT is usually organisation-wide, but must be answered per product. Options:
- (a) Answer at `product` level now; accept repetition across products. Simplest, and consistent with ADR 0004.
- (b) Later: an ADR adding organisation / product-family answers that products inherit (precedence would extend to option → release → HW rev → product → family → organisation).

Per-release activities (M6, M8–M11, M14) belong at `software` level, so carry-forward marks them "needs confirmation" on each new release, which is the desired behaviour.

The linter rejects the same id with a different level. **Fix levels before publishing `common` 1.1.0**; changing them later is a breaking change.

### 4.2 Same words, different meanings
- **"Component."** CRA: an integrated part, possibly itself a product with digital elements. 62443-4-2: a building block of an industrial automation and control system (IACS), of one of four types. SSDF/CISA: a third-party software dependency. P21/M13 mean the SSDF sense.
- **"Risk assessment."** CRA Art. 13: product lifecycle risk, including intended and foreseeable use. 62443-3-2: system-level, zones and conduits, owned by integrator/asset owner. 62443-4-1 SR-1/SR-2: product security context + threat model. SSDF PW.1.1: risk modelling of the software design. The questions are related but not interchangeable.
- **"SBOM" vs. "inventory."** 4-2 CR 7.8† is a runtime capability (the component can report what is installed), not an SBOM document. Do not derive M14 from it.
- **"Secure by default."** CRA: the shipped state. SSDF PW.9: default settings plus documenting them. 62443: least functionality plus hardening guidelines, and it may rely on compensating countermeasures in the environment (SG-2†). A 62443-compliant product can still fail CRA I.2(b).
- **"Security update."** CRA wants automatic, default-on, free updates. In OT practice the asset owner qualifies and applies patches (SUM-1 is about the vendor qualifying updates). Same fact (`update_mechanism`), opposite expectations. Packages must judge it differently, so do not encode a judgement in the label.
- **"Vulnerability" vs. "security-related issue."** 4-1 DM covers a broader class (any security defect). CRA Part II is about vulnerabilities. Fine for questions; matters for evidence reuse.
- **"Disclosure."** CRA Part II(4) public disclosure after fix (delay allowed). SSDF RV.1.3 = having a disclosure policy. 4-1 DM-5 = disclosing to users.

### 4.3 Booleans that are too coarse
- **Encryption, logging, DoS, testing:** "yes" can mean one interface or all. Use `choice` where a spec branches on the distinction (P12, P13, M14, P14); otherwise keep a boolean and let the package ask a refinement with a `condition`.
- **MFA:** 62443 distinguishes MFA for untrusted networks vs. all networks†, and human users (CR 1.1) vs. devices/processes (CR 1.2). The existing three booleans cover users/admins only. Consider `mfa_for_remote_access` (boolean, software, `implied_by` `mfa_for_all_users`) when the 62443 package is written.
- **Outcome questions:** "Is the product free of known exploitable vulnerabilities?" is a conclusion, not a fact. Ask process facts (M9, M12) and let each package raise findings.
- **Multi-select:** `choice` is single-valued. Split interfaces (P2, P3, P5) and 62443 component types into separate questions.

### 4.4 Capability vs. enablement
The architecture models features as hardware capability + software enablement. P2/P3/P5 are capability `choice`s at hardware level. P4 is the software-level enablement. P16 (secure boot) depends on both a hardware root of trust and its software activation. Either split it (`has_hardware_root_of_trust` hardware + `secure_boot_enabled` software) or keep it at `software` level with guidance. Splitting matches the architecture better.

### 4.5 `implied_by` rules
Use only strict logical implications. Proposed:
- `uses_mfa` ⇐ `mfa_for_admin_access` or `mfa_for_all_users`
- `requires_user_authentication` ⇐ `uses_mfa`
- `has_data_connection` ⇐ interface `present` / services `!= none`. Derive true only, never false: a disabled interface may still count as reasonably foreseeable use under CRA.
- `security_testing_before_release` ⇐ `penetration_testing_performed`
- `signs_releases` ⇐ `verifies_update_authenticity`
- `has_vulnerability_contact` ⇐ `has_cvd_policy` (medium; optional)

Do **not** add: risk assessment ⇐ threat modelling; due diligence ⇐ SBOM; secure defaults ⇐ no listening services.

Derivation across levels works: `apps/assessments/resolution.py` resolves every question for the configuration (all levels) into one data set before `_apply_derived` runs to a fixpoint, so e.g. `has_data_connection` (software) can be derived from `network_interface_capability` (hardware).

### 4.6 Collisions with existing ids
The demo `has_wireless` (boolean, hardware) is the same fact as P3 with a different type. Use the new id and leave the demo alone, or migrate the demo. Reusing the id with type `choice` is a linter error.

### 4.7 Activating non-legislation packages
62443 and SSDF are not jurisdiction-bound legislation. Under the architecture's source types, 62443 is a harmonised-standard candidate (EN IEC 62443-4-1/A11 and 4-2/A11 are being amended for CRA) or a customer requirement. SSDF/CISA is a customer requirement for US federal supply. Both are selected per product, not by target market. Their questions only appear when the package is selected, so shared questions should be phrased neutrally.

### 4.8 Answers are self-attested
Process booleans are claims. Plan evidence links (ADR 0011) per question, so that, for example, M18 → the published CVD policy URL. The crosswalk in section 2 is the reuse key.

### 4.9 Guidance text
Guidance text must stay in our own words (schema description). Do not paste 62443 requirement titles into `label` or `guidance`; cite the id in the package's `ref` field instead.

---

## 5. Sources

**Repository (read in full or in the relevant parts; verified):**
- `packages/common/1.0.0.json`
- `docs/adr/0015-shared-question-library.md`
- `docs/adr/0012-eu-cra-package.md`
- `docs/adr/0004-answer-levels-and-precedence.md`
- `schemas/question-set.schema.json` (`$defs.question`)
- `packages/eu-cra-partial/1.0.0.json`
- `packages/demo-widget-safety/*.json`
- `docs/architecture.md` (packages, questions, answer inheritance, open questions)
- `apps/packages/ruleengine.py` (operators; comparisons are number-only)
- `apps/packages/linting.py` (numeric type check)

**Web (WebSearch snippets only; WebFetch blocked by the egress proxy for all domains tried):**
- NIST SSDF project page and SP 800-218r1 ipd announcement: csrc.nist.gov/pubs/sp/800/218/r1/ipd, csrc.nist.gov/News/2025/draft-ssdf-version-1-2. Verified: SSDF 1.2 draft published 17 Dec 2025; comments to 30 Jan 2026.
- SSDF task snippets (myctrl.tools, edu.chainguard.dev SSDF table, cybersecurity.cd.foundation). Verified ids: PO.1.1, PO.1.2, PO.3, PO.4, PO.5, PS.1, PS.2, PS.3, PS.3.2 (SBOM/provenance), PW.1.1–PW.1.3, PW.2, PW.4.4, RV.1.1, RV.1.3 (disclosure policy), RV.2.2, RV.3. Snippets disagreed on PO.1.3 and PW.4.5; PO.1.3 is used here from memory as "communicate requirements to third parties" (unverified).
- CISA Secure Software Development Attestation Form (cisa.gov/secure-software-attestation-form; summaries by Davis Wright Tremaine, Endor Labs, Chainguard). Verified: released 11 Mar 2024. Four attestation areas: secure build environments; trusted source code supply chain; provenance of internal and third-party code; automated vulnerability checks plus a disclosure programme and a policy on vulnerabilities before release.
- IEC 62443-4-1 overviews (jtsec.es requirement table, isa.org TOC, VDE/IEC preview snippets, versprite.com). Verified ids: practices SM, SR, SD, SI, SVV, DM, SUM, SG; SM-1, SM-9, SM-10, SM-12 (topic disagreed between sources), SR-1, SR-2, SD-1, SD-4, SVV-1, SVV-3, SVV-4, DM-1, DM-4, DM-5, SUM-1, SUM-3.
- IEC 62443-4-2 overviews (teeptrak.com, incibe.es, CIP readthedocs assessment pages, GE Vernova and mGuard evaluation PDFs). Verified: FR1–FR7 structure; EDR/HDR/NDR/SAR categories; CR 1.1, CR 1.2, CR 1.7, CR 2.8, CR 3.4, CR 7.1 exist. One snippet listed "CR 3.10" and "CR 3.14", but from memory these are component-specific (EDR/HDR/NDR) requirements. Unresolved; marked †.
- ENISA/JRC "Cyber Resilience Act Requirements Standards Mapping" (enisa.europa.eu publication page; industrialcyber.co summary; streamlex.eu). Verified: the report exists (April 2024). For Part II, ISO/IEC 30111 covers 5 of 8 requirements and ISO/IEC 29147 covers 4. **The per-item 62443 mapping could not be read; section 2 is from memory.**
- CRA standardisation: cencenelec.eu (EN IEC 62443 to CRA event, March 2026 webinar slides), din.de, cyberresilienceact.eu. Verified: EN 40000-1-1/-1-2/-1-3 horizontal drafts (vocabulary, principles, vulnerability handling) under approval as of March 2026; EN IEC 62443-4-1/A11 and 62443-4-2/A11 amendments for CRA alignment; July 2026 draft amendment pushing standardisation deadlines back two months.
- CRA Art. 14 timing (usd.de, itemis.com, cyberresilienceact.eu/reporting). Verified: reporting obligations apply from 11 Sep 2026; 24 h early warning, 72 h notification; ENISA Single Reporting Platform.

**From memory (unverified):** all ids marked †; full 62443-4-1 requirement numbering (SM-2…SM-13, SR-3…SR-5, SD-2/SD-3, SI-1/SI-2, SVV-2/SVV-5, DM-2/DM-3/DM-6, SUM-2/SUM-4/SUM-5, SG-1…SG-7); 62443-4-2 CR numbers other than those verified; 62443 MFA enhancements by network trust; SSDF tasks PO.2.x, PO.5.x, PS.1.1, PS.2.1, PS.3.1, PW.4.1, PW.5–PW.9, RV.1.2, RV.2.1; CRA article sub-paragraph numbers beyond those in the brief (Art. 13(1)/(2)/(3)/(5)/(6)/(8), Annex II, Annex VII); CISA attestation scope, exemptions and plan-of-action details; all confidence ratings in section 2.
