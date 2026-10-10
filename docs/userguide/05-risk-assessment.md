# Risk assessment

Alongside regulatory assessments, Aavistin keeps a product-level **risk
register** — threats, hazards and the assets they affect — rated against
one or more risk methods (e.g. a 5×5 severity/likelihood matrix), and
tracked through to treatment.

## Entries

A risk register entry is one of three types:

- **Asset** — something worth protecting (e.g. "firmware", "user data").
- **Threat** — something that could compromise an asset's
  confidentiality, integrity or availability.
- **Hazard** — something that could cause physical or safety harm, with
  its own causes.

Threats and hazards can be linked to each other where they share a root
cause.

## Adding and editing entries

Editors open a configuration's risk register and choose **+ Add entry**.
Pick the type (asset, threat or hazard), give it a label and an optional
description, and choose where it applies (see below). A threat also
names the asset it targets and the property it violates — the choices
come from the risk methods your administrator has approved.

One attack can break several properties at once — remote code execution
may expose data, change it and stop the device. When adding a threat,
tick every property it breaks: Aavistin adds one threat per property,
labelled e.g. "Remote code execution (Integrity)". They are separate
because each property is rated and treated on its own: encryption may
handle confidentiality while integrity still needs signing.

To enter several entries in a row, use **Save and add another**: it
saves the entry and opens a fresh form with the same type, scope and
(for threats) asset already chosen, so each next entry only needs its
label.

The **Edit** button on an entry changes its label, description, scope
and (for threats) asset and property. The type can't be changed once an
entry exists; add a new entry instead.

Entries belong to the product's register, so an entry added from one
configuration appears in every configuration it applies to.

**Delete** on an entry asks for confirmation first and lists what goes
with it. Threats that targeted a deleted asset stay, without an asset.

## Rating an entry in the app

Open an entry from the register:

- **Asset** — under *Asset rating*, set how severe it would be if its
  confidentiality, integrity or availability were compromised.
- **Threat** — add its *consequences* (what happens if it succeeds, by
  impact category). A new consequence starts at the asset's rating for
  the property the threat violates; choosing another value needs a
  justification. The threat's severity is its worst consequence. Then
  set its *likelihood* under each method that covers that property.
- **Hazard** — set severity and likelihood under each safety method.

The method's matrix then shows the level (e.g. *high*) and what it
means (*must treat*, *justify*, *accept*).

## Treatment and controls

For each rated method, **+ Add treatment** records the decision
(mitigate, accept, transfer or avoid) and the residual severity and
likelihood after treatment. A justification is required unless you
mitigate down to a residual the method accepts outright.

On a threat, **+ Link a control** creates a control (e.g. "Secure boot")
or links one that already exists for the product, so one control can
mitigate several threats. Its status (planned, implemented, verified)
can be changed in place.

Hazard causes and their controls are still edited by an administrator.

## Baseline vs. scoped entries

An entry is **baseline** by default — it applies to the whole product.
It can instead be **scoped** to a specific hardware variant, software
release or option, with a justification, when the risk genuinely differs
there (e.g. a wireless-only hazard that doesn't apply to a wired
variant).

## Rating and treatment

Each entry gets one rating per applicable method (severity × likelihood,
or however that method defines it). A **Control** — a mitigation, its
own entity — can be linked to a threat or a hazard's cause. Once a
control is in place, the entry's **residual rating** (after treatment)
is what's checked against the method's acceptance thresholds: an entry
whose residual rating is still unacceptable under any applicable method
needs further treatment before it's considered handled.

## Approval

Like assessments, a product's risk register can be **approved** per
configuration view, recording exactly which method and catalog versions
were used — and goes **stale** the same way if the underlying data
changes afterwards.
