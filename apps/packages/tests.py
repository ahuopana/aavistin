import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from .diffing import diff_packages
from .fixtures_runner import run_fixtures
from .importer import PackageImportError, approve_package, import_package
from .linting import lint_package
from .models import PackageStatus, RequirementPackage
from .ruleengine import RuleEngineError, evaluate

DEMO_DIR = Path(settings.BASE_DIR) / "packages" / "demo-widget-safety"


def load_demo(version: str) -> dict:
    with (DEMO_DIR / f"{version}.json").open() as f:
        return json.load(f)


class RuleEngineTests(TestCase):
    def test_literals_pass_through(self):
        self.assertEqual(evaluate(True, {}), True)
        self.assertEqual(evaluate("x", {}), "x")
        self.assertEqual(evaluate(None, {}), None)

    def test_var_looks_up_data(self):
        self.assertEqual(evaluate({"var": "a"}, {"a": 5}), 5)
        self.assertIsNone(evaluate({"var": "missing"}, {}))
        self.assertEqual(evaluate({"var": ["missing", "fallback"]}, {}), "fallback")

    def test_boolean_operators(self):
        self.assertTrue(evaluate({"and": [True, True]}, {}))
        self.assertFalse(evaluate({"and": [True, False]}, {}))
        self.assertTrue(evaluate({"or": [False, True]}, {}))
        self.assertTrue(evaluate({"!": False}, {}))

    def test_comparisons(self):
        self.assertTrue(evaluate({">": [5, 3]}, {}))
        self.assertTrue(evaluate({"==": ["a", "a"]}, {}))
        self.assertFalse(evaluate({"!=": ["a", "a"]}, {}))

    def test_numeric_operator_rejects_non_number(self):
        with self.assertRaises(RuleEngineError):
            evaluate({">": ["a", 3]}, {})

    def test_if(self):
        self.assertEqual(evaluate({"if": [True, "yes", "no"]}, {}), "yes")
        self.assertEqual(evaluate({"if": [False, "yes", "no"]}, {}), "no")

    def test_in(self):
        self.assertTrue(evaluate({"in": ["a", ["a", "b"]]}, {}))

    def test_unknown_operator_raises(self):
        with self.assertRaises(RuleEngineError):
            evaluate({"exec": "import os"}, {})

    def test_malformed_expression_raises(self):
        with self.assertRaises(RuleEngineError):
            evaluate({"a": 1, "b": 2}, {})
        with self.assertRaises(RuleEngineError):
            evaluate(object(), {})


class LintingTests(TestCase):
    def test_unknown_question_reference(self):
        content = {
            "source": "x",
            "version": "1.0.0",
            "questions": [{"id": "a", "type": "boolean", "level": "product"}],
            "scope": {"include": {"var": "does_not_exist"}},
        }
        issues = lint_package(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        self.assertTrue(any(i["code"] == "unknown_question" for i in issues))

    def test_numeric_op_on_boolean_question_is_type_mismatch(self):
        content = {
            "source": "x",
            "version": "1.0.0",
            "questions": [{"id": "a", "type": "boolean", "level": "product"}],
            "scope": {"include": {">": [{"var": "a"}, 1]}},
        }
        issues = lint_package(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        self.assertTrue(any(i["code"] == "type_mismatch" for i in issues))

    def test_bad_date_and_date_order(self):
        content = {
            "source": "x",
            "version": "1.0.0",
            "questions": [],
            "scope": {"include": True},
            "dates_of_application": {"from": "2025-06-01", "until": "2024-01-01"},
        }
        issues = lint_package(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        self.assertTrue(any(i["code"] == "date_order" for i in issues))

    def test_namespace_shadow(self):
        RequirementPackage.objects.create(
            source="demo-widget-safety",
            version="0.9.0",
            package_type="legislation",
            jurisdiction="EU",
            content={"source": "demo-widget-safety", "version": "0.9.0"},
            is_official=True,
            status=PackageStatus.APPROVED,
        )
        content = {
            "source": "demo-widget-safety",
            "version": "1.0.0",
            "questions": [],
            "scope": {},
        }
        issues = lint_package(
            content,
            is_official=False,
            existing_packages=RequirementPackage.objects.all(),
        )
        self.assertTrue(any(i["code"] == "namespace_shadow" for i in issues))

    def test_supersedes_cycle(self):
        RequirementPackage.objects.create(
            source="x",
            version="1.0.0",
            package_type="legislation",
            jurisdiction="EU",
            content={
                "source": "x",
                "version": "1.0.0",
                "supersedes": [{"source": "x", "version": "2.0.0"}],
            },
            status=PackageStatus.APPROVED,
        )
        content = {
            "source": "x",
            "version": "2.0.0",
            "questions": [],
            "scope": {},
            "supersedes": [{"source": "x", "version": "1.0.0"}],
        }
        issues = lint_package(
            content, is_official=False, existing_packages=RequirementPackage.objects.all()
        )
        self.assertTrue(any(i["code"] == "supersedes_cycle" for i in issues))


class FixtureRunnerTests(TestCase):
    def test_demo_package_1_0_0_fixtures_all_pass(self):
        content = load_demo("1.0.0")
        report = run_fixtures(content)
        self.assertEqual(len(report), 4)
        self.assertTrue(all(r["passed"] for r in report), report)

    def test_demo_package_1_1_0_fixtures_all_pass(self):
        content = load_demo("1.1.0")
        report = run_fixtures(content)
        self.assertTrue(all(r["passed"] for r in report), report)

    def test_fixture_mismatch_is_reported(self):
        content = load_demo("1.0.0")
        content["fixtures"] = [
            {
                "id": "wrong",
                "answers": {
                    "has_power_source": True,
                    "rated_power_watts": 20,
                    "is_toy_widget": False,
                },
                "expected": {"in_scope": False},
            }
        ]
        report = run_fixtures(content)
        self.assertFalse(report[0]["passed"])


class DiffTests(TestCase):
    def test_diff_between_demo_versions(self):
        diff = diff_packages(load_demo("1.0.0"), load_demo("1.1.0"))
        self.assertEqual(diff["version"], {"from": "1.0.0", "to": "1.1.0"})
        self.assertIn("has_wireless", diff["sections"]["questions"]["added"])
        self.assertIn("wireless_action_required", diff["sections"]["finding_rules"]["added"])
        self.assertIn("wireless_interference_test", diff["sections"]["requirements"]["added"])
        self.assertIn("high_power", diff["sections"]["classifications"]["changed"])

    def test_diff_of_identical_content_is_empty(self):
        content = load_demo("1.0.0")
        diff = diff_packages(content, content)
        self.assertEqual(diff["sections"], {})
        self.assertNotIn("scope_changed", diff)


class ImportPipelineTests(TestCase):
    def test_schema_validation_rejects_missing_required_field(self):
        with self.assertRaises(PackageImportError):
            import_package({"source": "x", "type": "legislation"})

    def test_import_demo_package_reaches_fixtures_passed(self):
        package = import_package(load_demo("1.0.0"), is_official=True)
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)
        self.assertEqual(package.lint_errors, [])
        self.assertTrue(all(r["passed"] for r in package.fixture_report))
        self.assertIsNone(package.diff_from_previous)

    def test_cannot_approve_before_fixtures_passed(self):
        package = RequirementPackage.objects.create(
            source="x",
            version="1.0.0",
            package_type="legislation",
            jurisdiction="EU",
            content={"source": "x", "version": "1.0.0"},
            status=PackageStatus.LINTED,
        )
        with self.assertRaises(PackageImportError):
            approve_package(package)

    def test_approve_supersedes_previous_version(self):
        v1 = import_package(load_demo("1.0.0"), is_official=True)
        approve_package(v1)
        self.assertEqual(RequirementPackage.objects.get(pk=v1.pk).status, PackageStatus.APPROVED)

        v2 = import_package(load_demo("1.1.0"), is_official=True)
        self.assertEqual(v2.status, PackageStatus.FIXTURES_PASSED)
        self.assertIsNotNone(v2.diff_from_previous)
        self.assertEqual(v2.supersedes_package_id, v1.pk)

        approve_package(v2)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, PackageStatus.SUPERSEDED)
        self.assertEqual(v2.status, PackageStatus.APPROVED)

    def test_local_package_cannot_shadow_official_namespace(self):
        import_package(load_demo("1.0.0"), is_official=True)
        shadowing = dict(load_demo("1.1.0"))
        shadowing.pop("supersedes", None)
        package = import_package(shadowing, is_official=False)
        self.assertIn("namespace_shadow", [i["code"] for i in package.lint_report])
        self.assertEqual(package.status, PackageStatus.DRAFT)

    def test_legislation_creates_legal_obligations_flag(self):
        package = import_package(load_demo("1.0.0"))
        self.assertTrue(package.creates_legal_obligations)


class ManagementCommandTests(TestCase):
    def test_import_and_approve_via_management_commands(self):
        path = DEMO_DIR / "1.0.0.json"
        call_command("import_package", str(path), "--official")
        package = RequirementPackage.objects.get(source="demo-widget-safety", version="1.0.0")
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)

        call_command("approve_package", "demo-widget-safety", "1.0.0")
        package.refresh_from_db()
        self.assertEqual(package.status, PackageStatus.APPROVED)
