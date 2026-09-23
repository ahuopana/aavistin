"""Evidence storage, reuse and linking.

See docs/architecture.md, "Evidence": content-addressed file dedup,
reuse-over-re-upload, and delete protection tied to approval.
"""

import hashlib

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
    """
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
        "configuration__hardware_revision__hardware_variant__product": evidence.product,
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
