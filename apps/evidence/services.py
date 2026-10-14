"""Evidence storage, reuse and linking.

See docs/architecture.md, "Evidence": content-addressed file dedup,
reuse-over-re-upload, and delete protection tied to approval.
"""

import hashlib

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.assessments.models import Assessment, AssessmentStatus
from apps.risk.models import RiskAssessment, RiskAssessmentStatus

from .models import Evidence, EvidenceFile, EvidenceLink, EvidenceTargetType


class EvidenceError(Exception):
    pass


class EvidenceInUseError(EvidenceError):
    pass


def _checksum(django_file) -> str:
    hasher = hashlib.sha256()
    for chunk in django_file.chunks():
        hasher.update(chunk)
    django_file.seek(0)
    return hasher.hexdigest()


def store_evidence_file(django_file, *, actor=None) -> EvidenceFile:
    """Stores an uploaded file once per distinct content, reusing an
    existing EvidenceFile with the same checksum instead of writing the
    bytes again (docs/architecture.md, "Evidence": "The blob is not the
    record").

    Raises EvidenceError when uploads are not configured (MEDIA_ROOT unset).
    """
    if not settings.UPLOADS_ENABLED:
        raise EvidenceError(
            "File uploads are not enabled on this server (MEDIA_ROOT is not configured). "
            "Add a link or reference note instead."
        )
    checksum = _checksum(django_file)
    existing = EvidenceFile.objects.filter(checksum=checksum).first()
    if existing is not None:
        return existing

    evidence_file = EvidenceFile(
        checksum=checksum,
        content_type=getattr(django_file, "content_type", "") or "",
        size=django_file.size,
        uploaded_by=actor,
    )
    evidence_file.file.save(django_file.name, django_file, save=False)
    try:
        with transaction.atomic():
            evidence_file.save()
    except IntegrityError:
        # Lost a race with a concurrent upload of the same content: use
        # the EvidenceFile that won it and drop the copy just written.
        evidence_file.file.delete(save=False)
        return EvidenceFile.objects.get(checksum=checksum)
    return evidence_file


def suggest_evidence(product):
    """Existing evidence for this product, offered before "upload, link
    or note something new" (docs/architecture.md, "Evidence": "Reuse
    over re-upload").
    """
    return Evidence.objects.filter(product=product).order_by("title")


def link_evidence(evidence, *, control=None, requirement=None, actor=None) -> EvidenceLink:
    """Attaches evidence to exactly one target: a Control, or a
    requirement given as (source, version, requirement_id).
    """
    if (control is None) == (requirement is None):
        raise EvidenceError("pass exactly one of control or requirement")

    if control is not None:
        link = EvidenceLink(
            evidence=evidence,
            target_type=EvidenceTargetType.CONTROL,
            control=control,
            created_by=actor,
        )
    else:
        source, version, requirement_id = requirement
        link = EvidenceLink(
            evidence=evidence,
            target_type=EvidenceTargetType.REQUIREMENT,
            requirement_source=source,
            requirement_version=version,
            requirement_id=requirement_id,
            created_by=actor,
        )
    link.full_clean()
    link.save()
    return link


def unlink_evidence(link: EvidenceLink) -> None:
    link.delete()


def _evidence_id_in_risk_snapshot(snapshot: dict | None, evidence_id: int) -> bool:
    if not snapshot:
        return False
    for control in snapshot.get("controls", []):
        for fingerprint in control.get("evidence", []):
            if fingerprint.get("evidence_id") == evidence_id:
                return True
    return False


def _evidence_id_in_assessment_snapshot(snapshot: dict | None, evidence_id: int) -> bool:
    if not snapshot:
        return False
    for result in snapshot.get("results", []):
        for fingerprints in result.get("requirement_evidence", {}).values():
            for fingerprint in fingerprints:
                if fingerprint.get("evidence_id") == evidence_id:
                    return True
    return False


def _referenced_by_approved_work(evidence: Evidence) -> bool:
    """Precise: blocks deletion only if this evidence's id actually
    appears inside an approved (frozen) snapshot -- apps.risk.approval's
    `_control_evidence_fingerprint` and apps.assessments.evaluation's
    `_requirement_evidence_fingerprint` both embed `evidence_id`, so a
    live link that was never captured in an approved snapshot (added
    after approval, or never approved at all) doesn't block deletion.
    """
    product_filter = {
        "configuration__software_release__product": evidence.product,
    }

    if evidence.links.filter(target_type=EvidenceTargetType.CONTROL).exists():
        risk_assessments = RiskAssessment.objects.filter(
            status=RiskAssessmentStatus.APPROVED, **product_filter
        )
        if any(_evidence_id_in_risk_snapshot(ra.snapshot, evidence.id) for ra in risk_assessments):
            return True

    if evidence.links.filter(target_type=EvidenceTargetType.REQUIREMENT).exists():
        assessments = Assessment.objects.filter(status=AssessmentStatus.APPROVED, **product_filter)
        if any(_evidence_id_in_assessment_snapshot(a.snapshot, evidence.id) for a in assessments):
            return True

    return False


def delete_evidence(evidence: Evidence) -> None:
    if _referenced_by_approved_work(evidence):
        raise EvidenceInUseError(
            f"{evidence}: referenced by an approved assessment or risk assessment "
            f"and cannot be deleted"
        )

    evidence_file = evidence.file
    evidence.delete()

    if evidence_file is not None and not evidence_file.evidence.exists():
        evidence_file.file.delete(save=False)
        evidence_file.delete()


def parse_requirement_ref(raw: str) -> tuple[str, str, str] | None:
    """``"source|version|requirement_id"`` -> tuple, as the UI passes a
    requirement in a single form value or query parameter."""
    parts = raw.split("|", 2) if raw else []
    return tuple(parts) if len(parts) == 3 and all(parts) else None


def requirement_choices(product) -> list[dict]:
    """Requirements in force for any configuration of ``product``, from the
    current evaluation: ``{"ref", "source", "version", "id", "label",
    "reference"}`` (``ref`` is the form value for `parse_requirement_ref`).
    Requirements are read from package content, never hard-coded
    (CLAUDE.md), and evidence can still be linked to others by hand.
    """
    from apps.assessments.evaluation import evaluate_configuration
    from apps.packages.models import RequirementPackage
    from apps.products.models import Configuration

    choices: dict[tuple[str, str, str], dict] = {}
    contents: dict[int, dict] = {}
    for configuration in Configuration.objects.filter(software_release__product=product):
        for result in evaluate_configuration(configuration)["results"]:
            if not result["in_scope"]:
                continue
            package_id = result["package_id"]
            if package_id not in contents:
                package = RequirementPackage.objects.get(pk=package_id)
                contents[package_id] = {
                    item["id"]: item for item in package.content.get("requirements", [])
                }
            for requirement_id in result["requirements"]:
                key = (result["source"], result["version"], requirement_id)
                item = contents[package_id].get(requirement_id, {})
                choices.setdefault(
                    key,
                    {
                        "ref": "|".join(key),
                        "source": key[0],
                        "version": key[1],
                        "id": requirement_id,
                        "label": item.get("label") or requirement_id,
                        "reference": item.get("ref", ""),
                    },
                )
    return sorted(choices.values(), key=lambda c: (c["source"], c["reference"], c["id"]))


def evidence_for_requirement(product, source: str, version: str, requirement_id: str):
    """Live evidence links of ``product`` for one requirement."""
    return EvidenceLink.objects.filter(
        evidence__product=product,
        target_type=EvidenceTargetType.REQUIREMENT,
        requirement_source=source,
        requirement_version=version,
        requirement_id=requirement_id,
    ).select_related("evidence")


def copy_links(old: Evidence, new: Evidence, *, actor=None) -> int:
    """Relink what ``old`` backed to its replacement ``new`` (the review
    step of superseding, docs/architecture.md "Evidence"). The old links
    stay until someone unlinks them. Returns how many links were added."""
    added = 0
    for link in old.links.all():
        if new.links.filter(
            target_type=link.target_type,
            control_id=link.control_id,
            requirement_source=link.requirement_source,
            requirement_version=link.requirement_version,
            requirement_id=link.requirement_id,
        ).exists():
            continue
        if link.control_id:
            link_evidence(new, control=link.control, actor=actor)
        else:
            link_evidence(
                new,
                requirement=(
                    link.requirement_source,
                    link.requirement_version,
                    link.requirement_id,
                ),
                actor=actor,
            )
        added += 1
    return added
