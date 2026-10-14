import hashlib
import io
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pypdf import PdfReader

from apps.accounts.models import User
from apps.assessments.models import Assessment
from apps.assessments.services import approve_assessment
from apps.core.tests import DashboardFixture
from apps.orgs.models import Role, RoleAssignment

from .models import Report
from .services import ReportError, generate_draft, issue_report

SECTIONS = ["product", "hardware", "software", "options", "assessment", "evidence"]


class ReportFixture(DashboardFixture):
    def setUp(self):
        super().setUp()
        self.approver = User.objects.create_user(username="ann", password="x")
        RoleAssignment.objects.create(role=Role.APPROVER, user=self.approver, product=self.product)

    def approve(self):
        self._ready_answers()
        return approve_assessment(
            Assessment.objects.create(configuration=self.configuration), actor=self.approver
        )

    def issue(self, sections=SECTIONS):
        self.approve()
        return issue_report(self.configuration, sections, user=self.approver)


class DraftTests(ReportFixture):
    def test_draft_is_a_pdf_and_stores_nothing(self):
        self._ready_answers()
        pdf = generate_draft(self.configuration, SECTIONS, user=self.editor)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(Report.objects.count(), 0)

    def test_draft_needs_a_section(self):
        with self.assertRaises(ReportError):
            generate_draft(self.configuration, [], user=self.editor)

    def test_viewer_downloads_draft(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("reports:generate", args=[self.configuration.pk]),
            {"action": "draft", "sections": SECTIONS},
        )
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(Report.objects.count(), 0)


class IssueTests(ReportFixture):
    def test_unapproved_assessment_blocks_issue(self):
        with self.assertRaisesMessage(ReportError, "not approved"):
            issue_report(self.configuration, SECTIONS, user=self.approver)

    def test_report_without_snapshot_section_blocks_issue(self):
        self.approve()
        with self.assertRaises(ReportError):
            issue_report(self.configuration, ["product"], user=self.approver)

    def test_stale_assessment_blocks_issue(self):
        assessment = self.approve()
        Assessment.objects.filter(pk=assessment.pk).update(stale=True)
        with self.assertRaisesMessage(ReportError, "stale"):
            issue_report(self.configuration, SECTIONS, user=self.approver)

    def test_issue_stores_content_and_hashes(self):
        report = self.issue()
        self.assertRegex(report.report_id, r"^AAV-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertEqual(report.pdf_sha256, hashlib.sha256(bytes(report.pdf)).hexdigest())
        self.assertEqual(report.content["status"], "approved")
        self.assertEqual(report.content["sources"]["assessment"]["id"], report.assessment_id)
        self.assertEqual(report.generated_by, self.approver)
        self.assertIsNone(report.risk_assessment)

    def test_content_comes_from_the_frozen_snapshot(self):
        report = self.issue()
        self.assertTrue(report.content["assessment"]["frozen"])

    def test_only_approvers_can_issue(self):
        self.approve()
        self.client.force_login(self.viewer)
        self.client.post(
            reverse("reports:generate", args=[self.configuration.pk]),
            {"action": "issue", "sections": SECTIONS},
        )
        self.assertEqual(Report.objects.count(), 0)
        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("reports:generate", args=[self.configuration.pk]),
            {"action": "issue", "sections": SECTIONS},
        )
        report = Report.objects.get()
        self.assertRedirects(response, reverse("reports:detail", args=[report.report_id]))


class AccessTests(ReportFixture):
    def test_outsider_cannot_see_report(self):
        report = self.issue()
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(reverse("reports:detail", args=[report.report_id])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("reports:pdf", args=[report.report_id])).status_code, 404
        )

    def test_viewer_downloads_issued_pdf(self):
        report = self.issue()
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("reports:pdf", args=[report.report_id]))
        self.assertEqual(b"".join(response.streaming_content), bytes(report.pdf))

    def test_list_only_shows_visible_reports(self):
        self.issue()
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse("reports:list")), "AAV-")


class VerifyTests(ReportFixture):
    def test_anonymous_verifies_issued_report(self):
        report = self.issue()
        response = self.client.get(reverse("verify", args=[report.report_id]))
        self.assertContains(response, report.pdf_sha256)

    def test_unknown_id_is_not_found(self):
        response = self.client.get(reverse("verify", args=["AAV-AAAA-AAAA-AAAA"]))
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "cannot be verified", status_code=404)

    def test_uploaded_pdf_is_checked_against_the_hash(self):
        report = self.issue()
        url = reverse("verify", args=[report.report_id])
        match = self.client.post(url, {"pdf": SimpleUploadedFile("r.pdf", bytes(report.pdf))})
        self.assertContains(match, "identical")
        other = self.client.post(url, {"pdf": SimpleUploadedFile("r.pdf", b"%PDF-tampered")})
        self.assertContains(other, "does not match")

    def test_stale_source_is_flagged(self):
        report = self.issue()
        Assessment.objects.filter(pk=report.assessment_id).update(stale=True)
        response = self.client.get(reverse("verify", args=[report.report_id]))
        self.assertContains(response, "gone stale")


class PdfTextTests(ReportFixture):
    def test_pdf_carries_id_and_status(self):

        report = self.issue()
        text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(bytes(report.pdf))).pages)
        self.assertIn(report.report_id, text)
        self.assertRegex(text, re.compile(r"Page 1 of \d+"))
