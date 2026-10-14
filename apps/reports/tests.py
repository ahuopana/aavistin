import hashlib
import io
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pypdf import PdfReader

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment
from apps.assessments.services import approve_assessment
from apps.core.tests import DashboardFixture
from apps.core.version import aavistin_version
from apps.orgs.models import Role, RoleAssignment

from .content import build_content, document_type
from .models import Report
from .services import ReportError, generate_draft, issue_report
from .templatetags.report_tags import report_date, report_time

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


class ContentTests(ReportFixture):
    def build(self, sections=("assessment",), user=None, **kwargs):
        from django.utils import timezone

        return build_content(
            self.configuration,
            list(sections),
            title="T",
            generated_by=user or self.approver,
            generated_at=timezone.now(),
            approved=False,
            **kwargs,
        )

    def test_generator_is_named_with_their_role(self):
        self.assertEqual(self.build()["generated_by"], "ann, Approver")
        self.assertEqual(self.build(user=self.viewer)["generated_by"], "vera, Viewer")

    def test_document_type_follows_the_sections(self):
        self.assertEqual(
            document_type(["assessment", "risks"]), "Product Compliance and Risk Assessment Report"
        )
        self.assertEqual(document_type(["assessment"]), "Product Compliance Assessment Report")
        self.assertEqual(document_type(["mitigations"]), "Product Risk Assessment Report")
        self.assertEqual(document_type(["product"]), "Product Report")

    def test_classifications_use_package_labels(self):
        self._ready_answers()
        Answer.objects.filter(question_id="rated_power_watts").update(value=100)
        result = self.build()["assessment"]["results"][0]
        self.assertIn("High power widget", result["classifications"])
        self.assertNotIn("high_power", result["classifications"])

    def test_answers_read_as_text(self):
        self._ready_answers()
        values = {a["question"]: a["value"] for a in self.build()["assessment"]["answers"]}
        self.assertIn("No", values.values())
        self.assertNotIn("False", values.values())

    def test_shared_question_ids_get_their_label(self):
        from apps.core.tests import load_package
        from apps.packages.importer import approve_package, import_package

        from .content import _assessment

        approve_package(
            import_package(load_package("common", "1.2.0"), kind="question_set", is_official=True)
        )
        evaluation = {
            "as_of": "2026-10-14",
            "results": [],
            "findings": [],
            "resolved_answers": {
                "dos_resilience_measures": {
                    "value": True,
                    "needs_confirmation": False,
                    "origin": "",
                }
            },
        }
        answers = _assessment(evaluation, False, include_out_of_scope=False)["answers"]
        self.assertNotIn("dos_resilience_measures", answers[0]["question"])
        self.assertTrue(answers[0]["question"].endswith("?"))

    def test_out_of_scope_packages_are_optional(self):
        self._ready_answers()
        Answer.objects.filter(question_id="has_power_source").update(value=False)
        hidden = self.build()["assessment"]
        self.assertEqual(hidden["results"], [])
        self.assertEqual(hidden["out_of_scope_count"], 1)
        shown = self.build(include_out_of_scope=True)["assessment"]
        self.assertEqual([r["in_scope"] for r in shown["results"]], [False])

    def test_findings_are_sorted_by_level_and_flag_out_of_scope(self):
        self._ready_answers(has_wireless=True)
        Answer.objects.filter(question_id="rated_power_watts").update(value=100)
        findings = self.build()["assessment"]["findings"]
        self.assertEqual([f["level_id"] for f in findings], ["action_required", "caution"])
        self.assertEqual(findings[0]["level"], "Action required")
        self.assertFalse(findings[0]["out_of_scope"])
        Answer.objects.filter(question_id="has_power_source").update(value=False)
        findings = self.build()["assessment"]["findings"]
        self.assertTrue(all(f["out_of_scope"] for f in findings))

    def test_evidence_requirements_show_their_label(self):
        from apps.evidence.models import Evidence, EvidenceKind
        from apps.evidence.services import link_evidence

        evidence = Evidence.objects.create(
            product=self.product, title="Manual", kind=EvidenceKind.TEXT, reference_text="wiki"
        )
        link_evidence(
            evidence, requirement=("demo-widget-safety", "1.1.0", "provide_widget_manual")
        )
        item = self.build(sections=("evidence",))["evidence"][0]
        self.assertEqual(item["requirements"], ["Provide a safety manual with the widget"])

    def test_version_is_recorded(self):
        self.assertEqual(self.build()["aavistin_version"], aavistin_version())

    def test_version_prefers_the_environment(self):
        aavistin_version.cache_clear()
        with self.settings(), unittest_env("AAVISTIN_VERSION", "v1.2.3"):
            self.assertEqual(aavistin_version(), "v1.2.3")
        aavistin_version.cache_clear()


class unittest_env:
    def __init__(self, name, value):
        self.name, self.value = name, value

    def __enter__(self):
        import os

        self.old = os.environ.get(self.name)
        os.environ[self.name] = self.value

    def __exit__(self, *exc):
        import os

        if self.old is None:
            del os.environ[self.name]
        else:
            os.environ[self.name] = self.old


class FilterTests(ReportFixture):
    def test_time_is_human_friendly(self):
        self.assertEqual(
            report_time("2026-10-14T15:42:28.975282+00:00"), "14 October 2026, 15:42 UTC"
        )
        self.assertEqual(report_date("2026-10-04"), "4 October 2026")
        self.assertEqual(report_time(""), "")


class SummaryTests(ReportFixture):
    def rows(self, content, title):
        group = next(g for g in content["summary"] if g["title"] == title)
        return {r["label"]: r["value"] for r in group["rows"]}

    def test_assessment_summary_counts_findings_by_level(self):
        self._ready_answers(has_wireless=True)
        Answer.objects.filter(question_id="rated_power_watts").update(value=100)
        content = ContentTests.build(self, sections=("assessment",))
        rows = self.rows(content, "Assessment")
        self.assertEqual(rows["Findings: action required"], 1)
        self.assertEqual(rows["Findings: caution"], 1)
        self.assertEqual(rows["Findings: info"], 0)
        self.assertEqual(rows["Regulations in scope"], 1)
        self.assertEqual(rows["Requirements in force"], 2)

    def test_out_of_scope_findings_are_counted_separately(self):
        self._ready_answers(has_wireless=True)
        Answer.objects.filter(question_id="has_power_source").update(value=False)
        rows = self.rows(ContentTests.build(self, sections=("assessment",)), "Assessment")
        self.assertEqual(rows["Regulations out of scope"], 1)
        self.assertEqual(rows["Findings of out-of-scope regulations"], 1)

    def test_summary_has_only_the_selected_sections(self):
        self.assertEqual(ContentTests.build(self, sections=("product",))["summary"], [])
        titles = [g["title"] for g in ContentTests.build(self, sections=("evidence",))["summary"]]
        self.assertEqual(titles, ["Evidence"])

    def test_risk_mitigation_and_evidence_counts(self):
        from .summary import build_summary

        content = {
            "sections": ["risks", "mitigations", "evidence"],
            "risks": {
                "entries": [
                    {"type": "Threat", "ratings": [{"acceptance": "must_treat"}]},
                    {"type": "Threat", "ratings": [{"acceptance": "accept"}]},
                    {"type": "Hazard", "ratings": [{"acceptance": "must_treat"}]},
                    {"type": "Asset", "ratings": []},
                ]
            },
            "mitigations": {
                "treatments": [
                    {"treatment": "mitigate", "residual": {"acceptance": "accept"}},
                    {"treatment": "mitigate", "residual": {"acceptance": None}},
                ],
                "controls": [
                    {"status": "planned", "evidence_count": 0},
                    {"status": "verified", "evidence_count": 1},
                ],
            },
            "evidence": [
                {"sha256": "ab", "expired": True, "superseded": False},
                {"sha256": "", "expired": False, "superseded": True},
            ],
        }
        groups = {
            g["title"]: {r["label"]: r["value"] for r in g["rows"]} for g in build_summary(content)
        }
        self.assertEqual(groups["Risks"]["Threats"], 2)
        self.assertEqual(groups["Risks"]["Must treat"], 2)
        self.assertEqual(groups["Mitigations"]["Treatments: mitigate"], 2)
        self.assertEqual(groups["Mitigations"]["Controls without evidence"], 1)
        self.assertEqual(groups["Evidence"]["Expired"], 1)
        self.assertEqual(groups["Evidence"]["Files (with checksum)"], 1)

    def test_summary_is_printed_on_the_cover(self):
        self._ready_answers()
        pdf = generate_draft(self.configuration, ["assessment"], user=self.approver)
        text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("Summary", text)
        self.assertIn("Findings: action required", text)
