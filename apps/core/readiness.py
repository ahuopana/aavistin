"""Explains *why* a page is empty by checking what is configured.

An empty register or an assessment with no active packages usually means a
prerequisite is missing, and which one decides who can fix it: an editor
(target markets, answers) or an administrator (importing and approving
packages, which has no screen in the app). Each check is a plain dict that
``templates/core/_readiness.html`` renders as a checklist:

``{"label", "ok", "detail", "url", "url_label"}``
"""

from django.urls import reverse

from apps.packages.models import PackageKind, PackageStatus, RequirementPackage

ASK_ADMIN = "Ask an administrator to import and approve one."


def _check(label, ok, detail="", url="", url_label="", *, keep_detail=False):
    """A satisfied check drops its "how to fix it" text unless ``keep_detail``."""
    detail = detail if (not ok or keep_detail) else ""
    return {"label": label, "ok": ok, "detail": detail, "url": url, "url_label": url_label}


def _target_markets_check(configuration) -> dict:
    variant = configuration.hardware_revision.hardware_variant
    codes = sorted(variant.target_markets.values_list("code", flat=True))
    product_url = reverse("products:product_detail", args=[variant.product_id])
    if codes:
        return _check(f"Target markets set ({', '.join(codes)})", True)
    return _check(
        "Target markets set",
        False,
        f"Hardware variant “{variant.name}” has none. Target markets decide which "
        "requirement packages apply and what gets suggested.",
        product_url,
        "Open the product",
    )


def _approved(kind: str):
    return RequirementPackage.objects.filter(kind=kind, status=PackageStatus.APPROVED)


def register_readiness(configuration, *, pending_suggestions: int) -> list[dict]:
    """Prerequisites for the risk register of ``configuration``."""
    has_catalog = _approved(PackageKind.CATALOG).exists()
    questionnaire_url = reverse("assessments:configuration_detail", args=[configuration.pk])
    checks = [
        _target_markets_check(configuration),
        _check(
            "A risk method is available",
            _approved(PackageKind.METHOD).exists(),
            f"Methods define how risks are scored. {ASK_ADMIN}",
        ),
        _check(
            "A risk catalog is available",
            has_catalog,
            f"Catalogs suggest entries from your answers. {ASK_ADMIN} "
            "Without one, entries have to be added by hand.",
        ),
    ]
    if has_catalog and pending_suggestions:
        checks.append(
            _check(
                f"{pending_suggestions} suggested entries are waiting for review",
                True,
                "Reviewing suggestions in the app is not available yet.",
                keep_detail=True,
            )
        )
    elif has_catalog:
        checks.append(
            _check(
                "Suggestions from your answers",
                False,
                "None triggered yet. Answering the questionnaire may trigger some.",
                questionnaire_url,
                "Open the questionnaire",
            )
        )
    return checks


def assessment_readiness(configuration) -> list[dict]:
    """Prerequisites for a configuration to have active requirement packages."""
    variant = configuration.hardware_revision.hardware_variant
    codes = sorted(variant.target_markets.values_list("code", flat=True))
    checks = [_target_markets_check(configuration)]
    if codes:
        checks.append(
            _check(
                f"An approved requirement package exists for {', '.join(codes)}",
                False,
                "No approved package matches these markets. Ask an administrator to import "
                "and approve the relevant package.",
            )
        )
    return checks
