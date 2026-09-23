from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.assessments.models import Assessment, AssessmentStatus
from apps.orgs.models import Organisation, ProductFamily
from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareRelease,
)
from apps.risk.approval import build_snapshot, recompute_staleness
from apps.risk.models import Control, RiskAssessment, RiskAssessmentStatus

from .models import Evidence, EvidenceFile, EvidenceKind, EvidenceLink, EvidenceTargetType
from .services import (
    EvidenceError,
    EvidenceInUseError,
    delete_evidence,
    link_evidence,
    store_evidence_file,
    suggest_evidence,
    unlink_evidence,
)

User = get_user_model()


class EvidenceFixture(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.product = Product.objects.create(
            product_family=self.family, name="TempSense", slug="tempsense"
        )
        self.other_product = Product.objects.create(
            product_family=self.family, name="OtherWidget", slug="other-widget"
        )
        self.variant = HardwareVariant.objects.create(
            product=self.product, name="EU variant", slug="eu-variant"
        )
        self.revision = HardwareRevision.objects.create(hardware_variant=self.variant, label="A")
        self.release = SoftwareRelease.objects.create(product=self.product, version="1.0")
        self.configuration = Configuration.objects.create(
            name="TempSense EU 1.0",
            hardware_revision=self.revision,
            software_release=self.release,
        )
        self.user = User.objects.create_user(username="edna", password="x")
        self.control = Control.objects.create(product=self.product, name="Secure boot")

    def make_text_evidence(self, product=None, **kwargs):
        return Evidence.objects.create(
            product=product or self.product,
            title=kwargs.pop("title", "Vulnerability handling policy"),
            kind=EvidenceKind.TEXT,
            reference_text=kwargs.pop("reference_text", "See QMS wiki page 42"),
            **kwargs,
        )


class EvidenceValidationTests(EvidenceFixture):
    def test_text_kind_requires_reference_text(self):
        evidence = Evidence(product=self.product, title="SBOM", kind=EvidenceKind.TEXT)
        with self.assertRaises(ValidationError):
            evidence.full_clean()

    def test_link_kind_requires_url(self):
        evidence = Evidence(product=self.product, title="SBOM", kind=EvidenceKind.LINK)
        with self.assertRaises(ValidationError):
            evidence.full_clean()

    def test_file_kind_requires_file(self):
        evidence = Evidence(product=self.product, title="SBOM", kind=EvidenceKind.FILE)
        with self.assertRaises(ValidationError):
            evidence.full_clean()

    def test_kind_rejects_mismatched_field(self):
        evidence = Evidence(
            product=self.product,
            title="SBOM",
            kind=EvidenceKind.TEXT,
            reference_text="see wiki",
            external_url="https://example.org/sbom",
        )
        with self.assertRaises(ValidationError):
            evidence.full_clean()

    def test_valid_text_evidence_passes(self):
        evidence = self.make_text_evidence()
        evidence.full_clean()

    def test_is_expired(self):
        from datetime import date, timedelta

        evidence = self.make_text_evidence(valid_until=date.today() - timedelta(days=1))
        self.assertTrue(evidence.is_expired)

    def test_is_superseded(self):
        old = self.make_text_evidence(title="Policy v1")
        Evidence.objects.create(
            product=self.product,
            title="Policy v2",
            kind=EvidenceKind.TEXT,
            reference_text="see wiki v2",
            supersedes=old,
        )
        self.assertTrue(old.is_superseded)


class EvidenceLinkValidationTests(EvidenceFixture):
    def test_control_link_requires_control(self):
        evidence = self.make_text_evidence()
        link = EvidenceLink(evidence=evidence, target_type=EvidenceTargetType.CONTROL)
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_control_link_rejects_other_product_control(self):
        evidence = self.make_text_evidence(product=self.other_product)
        link = EvidenceLink(
            evidence=evidence, target_type=EvidenceTargetType.CONTROL, control=self.control
        )
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_control_link_rejects_requirement_fields(self):
        evidence = self.make_text_evidence()
        link = EvidenceLink(
            evidence=evidence,
            target_type=EvidenceTargetType.CONTROL,
            control=self.control,
            requirement_id="cra-annex-1-part-2",
        )
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_requirement_link_requires_all_three_fields(self):
        evidence = self.make_text_evidence()
        link = EvidenceLink(
            evidence=evidence,
            target_type=EvidenceTargetType.REQUIREMENT,
            requirement_source="eu-cra",
        )
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_requirement_link_rejects_control(self):
        evidence = self.make_text_evidence()
        link = EvidenceLink(
            evidence=evidence,
            target_type=EvidenceTargetType.REQUIREMENT,
            requirement_source="eu-cra",
            requirement_version="2024-2847@2026-09",
            requirement_id="annex-1-part-2",
            control=self.control,
        )
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_valid_control_link_passes(self):
        evidence = self.make_text_evidence()
        link = EvidenceLink(
            evidence=evidence, target_type=EvidenceTargetType.CONTROL, control=self.control
        )
        link.full_clean()

    def test_valid_requirement_link_passes(self):
        evidence = self.make_text_evidence()
        link = EvidenceLink(
            evidence=evidence,
            target_type=EvidenceTargetType.REQUIREMENT,
            requirement_source="eu-cra",
            requirement_version="2024-2847@2026-09",
            requirement_id="annex-1-part-2",
        )
        link.full_clean()


class StoreEvidenceFileTests(EvidenceFixture):
    def test_dedup_by_content(self):
        content = b"sbom contents"
        f1 = store_evidence_file(SimpleUploadedFile("sbom.json", content), actor=self.user)
        f2 = store_evidence_file(SimpleUploadedFile("sbom-copy.json", content), actor=self.user)
        self.assertEqual(f1.pk, f2.pk)
        self.assertEqual(EvidenceFile.objects.count(), 1)

    def test_different_content_creates_separate_files(self):
        f1 = store_evidence_file(SimpleUploadedFile("a.txt", b"one"))
        f2 = store_evidence_file(SimpleUploadedFile("b.txt", b"two"))
        self.assertNotEqual(f1.pk, f2.pk)
        self.assertEqual(EvidenceFile.objects.count(), 2)


class LinkingServiceTests(EvidenceFixture):
    def test_link_to_control(self):
        evidence = self.make_text_evidence()
        link = link_evidence(evidence, control=self.control, actor=self.user)
        self.assertEqual(link.target_type, EvidenceTargetType.CONTROL)
        self.assertEqual(link.control, self.control)

    def test_link_to_requirement(self):
        evidence = self.make_text_evidence()
        link = link_evidence(
            evidence,
            requirement=("eu-cra", "2024-2847@2026-09", "annex-1-part-2"),
            actor=self.user,
        )
        self.assertEqual(link.target_type, EvidenceTargetType.REQUIREMENT)
        self.assertEqual(link.requirement_id, "annex-1-part-2")

    def test_link_requires_exactly_one_target(self):
        evidence = self.make_text_evidence()
        with self.assertRaises(EvidenceError):
            link_evidence(evidence)
        with self.assertRaises(EvidenceError):
            link_evidence(
                evidence,
                control=self.control,
                requirement=("eu-cra", "1.0", "x"),
            )

    def test_unlink(self):
        evidence = self.make_text_evidence()
        link = link_evidence(evidence, control=self.control)
        unlink_evidence(link)
        self.assertFalse(EvidenceLink.objects.filter(pk=link.pk).exists())

    def test_suggest_evidence_is_product_scoped(self):
        self.make_text_evidence(title="Policy A")
        self.make_text_evidence(product=self.other_product, title="Policy B")
        titles = list(suggest_evidence(self.product).values_list("title", flat=True))
        self.assertEqual(titles, ["Policy A"])


class DeleteEvidenceTests(EvidenceFixture):
    def test_deletes_unreferenced_evidence(self):
        evidence = self.make_text_evidence()
        pk = evidence.pk
        delete_evidence(evidence)
        self.assertFalse(Evidence.objects.filter(pk=pk).exists())

    def test_file_removed_only_once_unreferenced(self):
        shared_file = store_evidence_file(SimpleUploadedFile("sbom.json", b"same bytes"))
        e1 = Evidence.objects.create(
            product=self.product,
            title="SBOM (product A copy)",
            kind=EvidenceKind.FILE,
            file=shared_file,
        )
        e2 = Evidence.objects.create(
            product=self.other_product,
            title="SBOM (product B copy)",
            kind=EvidenceKind.FILE,
            file=shared_file,
        )
        delete_evidence(e1)
        self.assertTrue(EvidenceFile.objects.filter(pk=shared_file.pk).exists())
        delete_evidence(e2)
        self.assertFalse(EvidenceFile.objects.filter(pk=shared_file.pk).exists())

    def test_blocks_delete_when_control_link_in_approved_risk_assessment(self):
        evidence = self.make_text_evidence()
        link_evidence(evidence, control=self.control)
        RiskAssessment.objects.create(
            configuration=self.configuration, status=RiskAssessmentStatus.APPROVED
        )
        with self.assertRaises(EvidenceInUseError):
            delete_evidence(evidence)
        self.assertTrue(Evidence.objects.filter(pk=evidence.pk).exists())

    def test_blocks_delete_when_requirement_link_in_approved_assessment(self):
        evidence = self.make_text_evidence()
        link_evidence(evidence, requirement=("eu-cra", "1.0", "annex-1-part-2"))
        Assessment.objects.create(
            configuration=self.configuration, status=AssessmentStatus.APPROVED
        )
        with self.assertRaises(EvidenceInUseError):
            delete_evidence(evidence)

    def test_does_not_block_when_no_approved_work(self):
        evidence = self.make_text_evidence()
        link_evidence(evidence, control=self.control)
        RiskAssessment.objects.create(configuration=self.configuration)  # draft
        delete_evidence(evidence)
        self.assertFalse(Evidence.objects.filter(pk=evidence.pk).exists())


class StalenessIntegrationTests(EvidenceFixture):
    def _approve(self):
        risk_assessment = RiskAssessment.objects.create(
            configuration=self.configuration,
            status=RiskAssessmentStatus.APPROVED,
            snapshot=build_snapshot(self.configuration),
        )
        return risk_assessment

    def test_new_control_evidence_link_makes_it_stale(self):
        risk_assessment = self._approve()
        evidence = self.make_text_evidence()
        link_evidence(evidence, control=self.control)
        self.assertTrue(recompute_staleness(risk_assessment))

    def test_unchanged_evidence_stays_fresh(self):
        evidence = self.make_text_evidence()
        link_evidence(evidence, control=self.control)
        risk_assessment = self._approve()
        self.assertFalse(recompute_staleness(risk_assessment))

    def test_expired_evidence_makes_it_stale(self):
        from datetime import date, timedelta

        evidence = self.make_text_evidence(valid_until=date.today() + timedelta(days=1))
        link_evidence(evidence, control=self.control)
        risk_assessment = self._approve()

        evidence.valid_until = date.today() - timedelta(days=1)
        evidence.save()
        self.assertTrue(recompute_staleness(risk_assessment))

    def test_superseded_evidence_makes_it_stale(self):
        evidence = self.make_text_evidence()
        link_evidence(evidence, control=self.control)
        risk_assessment = self._approve()

        Evidence.objects.create(
            product=self.product,
            title="Policy v2",
            kind=EvidenceKind.TEXT,
            reference_text="see wiki v2",
            supersedes=evidence,
        )
        self.assertTrue(recompute_staleness(risk_assessment))
