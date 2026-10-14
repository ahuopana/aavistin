# 20. Target markets on software releases

Status: Accepted

## Context

Target markets were set only on hardware variants, and only packages for those markets apply. That left standalone software, a main CRA case and Aavistin itself, without a place to say where it is sold (open question in `docs/architecture.md`). A firmware or app release may also be distributed in fewer markets than the hardware.

## Decision

- `SoftwareRelease` gets `target_markets`, edited like a hardware variant's and copied when a release is cloned.
- A configuration's **effective markets**: the intersection of the hardware variant's and the release's markets when both are set (it is sold only where both parts are); the release's alone or the variant's alone when only one is set; none when neither is.
- Readiness checks and package activation use the effective markets.

## Consequences

- Software-only products can declare markets on the release. A configuration still needed a hardware revision at this point; ADR 0038 makes it optional.
- Existing data keeps its behaviour: releases start with no markets, so the variant's markets apply.
