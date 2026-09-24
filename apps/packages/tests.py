import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from .catalog_engine import run_catalog_fixtures, triggered_entries
from .diffing import diff_packages
from .fixtures_runner import run_fixtures
from .importer import PackageImportError, approve_package, import_package
from .linting import lint_catalog, lint_method, lint_package
from .method_engine import evaluate_matrix, run_method_fixtures
from .models import PackageKind, PackageStatus, RequirementPackage
from .ruleengine import RuleEngineError, evaluate

DEMO_DIR = Path(settings.BASE_DIR) / "packages" / "demo-widget-safety"
PACKAGES_DIR = Path(settings.BASE_DIR) / "packages"


def load_demo(version: str) -> dict:
    with (DEMO_DIR / f"{version}.json").open() as f:
        return json.load(f)


def load_package(dirname: str, version: str) -> dict:
    with (PACKAGES_DIR / dirname / f"{version}.json").open() as f:
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

    def test_comparison_with_unanswered_question_is_false_not_an_error(self):
        # An unanswered question resolves to None; a numeric threshold
        # against it is simply not yet true, not a type error.
        self.assertFalse(evaluate({">": [{"var": "missing"}, 80]}, {}))
        self.assertFalse(evaluate({"<": [{"var": "missing"}, 80]}, {}))

    def test_arithmetic_with_none_still_raises(self):
        with self.assertRaises(RuleEngineError):
            evaluate({"+": [{"var": "missing"}, 1]}, {})

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

    def test_classification_var_allowed_in_finding_rules_and_routes(self):
        content = {
            "source": "x",
            "version": "1.0.0",
            "questions": [{"id": "a", "type": "boolean", "level": "product"}],
            "scope": {"include": True},
            "classifications": [{"id": "high", "label": "High", "when": {"var": "a"}}],
            "assessment_routes": [
                {"id": "route", "label": "Route", "allowed_when": {"var": "class__high"}}
            ],
            "finding_rules": [
                {
                    "id": "f",
                    "level": "caution",
                    "when": {"var": "class__high"},
                    "message": "m",
                }
            ],
        }
        issues = lint_package(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        self.assertEqual(issues, [])

    def test_unknown_classification_reference(self):
        content = {
            "source": "x",
            "version": "1.0.0",
            "questions": [],
            "scope": {"include": True},
            "classifications": [{"id": "high", "label": "High", "when": True}],
            "finding_rules": [
                {
                    "id": "f",
                    "level": "caution",
                    "when": {"var": "class__does_not_exist"},
                    "message": "m",
                }
            ],
        }
        issues = lint_package(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        self.assertTrue(any(i["code"] == "unknown_classification" for i in issues))

    def test_classification_var_not_allowed_outside_routes_and_finding_rules(self):
        # class__ vars only resolve inside assessment_routes/finding_rules
        # (see evaluate_configuration); elsewhere it's just an undeclared
        # question, same as any other unknown var.
        content = {
            "source": "x",
            "version": "1.0.0",
            "questions": [],
            "scope": {"include": {"var": "class__high"}},
            "classifications": [{"id": "high", "label": "High", "when": True}],
        }
        issues = lint_package(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        self.assertTrue(any(i["code"] == "unknown_question" for i in issues))

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

    def test_import_eu_cra_package_reaches_fixtures_passed(self):
        package = import_package(load_package("eu-cra", "1.0.0"), is_official=True)
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)
        self.assertEqual(package.lint_report, [])
        self.assertTrue(all(r["passed"] for r in package.fixture_report), package.fixture_report)


class ManagementCommandTests(TestCase):
    def test_import_and_approve_via_management_commands(self):
        path = DEMO_DIR / "1.0.0.json"
        call_command("import_package", str(path), "--official")
        package = RequirementPackage.objects.get(source="demo-widget-safety", version="1.0.0")
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)

        call_command("approve_package", "demo-widget-safety", "1.0.0")
        package.refresh_from_db()
        self.assertEqual(package.status, PackageStatus.APPROVED)


class MethodEngineTests(TestCase):
    def test_matrix_thresholds(self):
        content = load_package("default-cia-5x5", "1.0.0")
        self.assertEqual(evaluate_matrix(content, 2, 2)["level"], "low")
        self.assertEqual(evaluate_matrix(content, 3, 3)["level"], "medium")
        self.assertEqual(evaluate_matrix(content, 5, 4)["level"], "high")

    def test_acceptance_follows_level(self):
        content = load_package("default-cia-5x5", "1.0.0")
        result = evaluate_matrix(content, 5, 5)
        self.assertEqual(result, {"level": "high", "acceptance": "must_treat"})

    def test_default_cia_5x5_fixtures_pass(self):
        content = load_package("default-cia-5x5", "1.0.0")
        report = run_method_fixtures(content)
        self.assertTrue(all(r["passed"] for r in report), report)


class MethodLintTests(TestCase):
    def test_matrix_level_missing_from_acceptance_is_error(self):
        content = {
            "source": "x",
            "kind": "method",
            "version": "1.0.0",
            "properties": ["confidentiality"],
            "severity": {"scale": [1, 5], "labels": ["a", "b", "c", "d", "e"]},
            "likelihood": {"scale": [1, 5], "labels": ["a", "b", "c", "d", "e"]},
            "matrix": [{"level": "extreme"}],
            "acceptance": {"low": "accept"},
        }
        issues = lint_method(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        self.assertTrue(any(i["code"] == "unmapped_matrix_level" for i in issues))

    def test_matrix_referencing_unknown_variable_warns(self):
        content = {
            "source": "x",
            "kind": "method",
            "version": "1.0.0",
            "properties": ["confidentiality"],
            "severity": {"scale": [1, 5], "labels": ["a", "b", "c", "d", "e"]},
            "likelihood": {"scale": [1, 5], "labels": ["a", "b", "c", "d", "e"]},
            "matrix": [{"when": {"var": "mystery"}, "level": "low"}],
            "acceptance": {"low": "accept"},
        }
        issues = lint_method(
            content, is_official=False, existing_packages=RequirementPackage.objects.none()
        )
        matches = [i for i in issues if i["code"] == "unknown_matrix_variable"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["severity"], "warning")


class CatalogEngineTests(TestCase):
    def test_triggers_fire_from_context(self):
        content = load_package("demo-widget-risks", "1.0.0")
        triggered = triggered_entries(content, {"has_wireless": True, "rated_power_watts": 20})
        self.assertIn("wireless_eavesdropping", triggered)
        self.assertIn("unauthorized_wireless_access", triggered)
        self.assertNotIn("overheating_fire", triggered)

    def test_no_triggers_when_context_is_negative(self):
        content = load_package("demo-widget-risks", "1.0.0")
        triggered = triggered_entries(content, {"has_wireless": False, "rated_power_watts": 5})
        self.assertEqual(triggered, [])

    def test_demo_catalog_fixtures_pass(self):
        content = load_package("demo-widget-risks", "1.0.0")
        report = run_catalog_fixtures(content)
        self.assertTrue(all(r["passed"] for r in report), report)


class CatalogLintTests(TestCase):
    def test_unknown_trigger_question_is_warning_not_error(self):
        content = {
            "source": "x",
            "kind": "catalog",
            "version": "1.0.0",
            "applies_to_methods": ["default-cia-5x5"],
            "entries": [
                {
                    "id": "t1",
                    "entry_type": "threat",
                    "label": "Threat 1",
                    "violates": "confidentiality",
                    "trigger": {"var": "some_future_question"},
                }
            ],
        }
        issues = lint_catalog(
            content,
            is_official=False,
            existing_packages=RequirementPackage.objects.none(),
            known_question_ids=set(),
        )
        matches = [i for i in issues if i["code"] == "unknown_trigger_question"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["severity"], "warning")

    def test_known_trigger_question_is_clean(self):
        content = {
            "source": "x",
            "kind": "catalog",
            "version": "1.0.0",
            "applies_to_methods": ["default-cia-5x5"],
            "entries": [
                {
                    "id": "t1",
                    "entry_type": "threat",
                    "label": "Threat 1",
                    "violates": "confidentiality",
                    "trigger": {"var": "has_wireless"},
                }
            ],
        }
        issues = lint_catalog(
            content,
            is_official=False,
            existing_packages=RequirementPackage.objects.none(),
            known_question_ids={"has_wireless"},
        )
        self.assertEqual(issues, [])


class MethodCatalogImportPipelineTests(TestCase):
    def test_import_method_package(self):
        package = import_package(
            load_package("default-cia-5x5", "1.0.0"), kind=PackageKind.METHOD, is_official=True
        )
        self.assertEqual(package.kind, PackageKind.METHOD)
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)
        self.assertEqual(package.package_type, "")
        self.assertEqual(package.jurisdiction, "")

    def test_import_catalog_references_known_questions_cleanly(self):
        import_package(load_demo("1.1.0"), is_official=True)
        package = import_package(
            load_package("demo-widget-risks", "1.0.0"),
            kind=PackageKind.CATALOG,
            is_official=True,
        )
        self.assertEqual(package.lint_report, [])
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)

    def test_import_catalog_before_its_questions_exist_only_warns(self):
        package = import_package(
            load_package("demo-widget-risks", "1.0.0"),
            kind=PackageKind.CATALOG,
            is_official=True,
        )
        # Still reaches fixtures_passed: unknown_trigger_question is a
        # warning, not an error, and doesn't block linted -> fixtures.
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)
        self.assertTrue(any(i["code"] == "unknown_trigger_question" for i in package.lint_report))

    def test_method_and_requirement_packages_share_the_source_namespace(self):
        import_package(
            load_package("default-cia-5x5", "1.0.0"), kind=PackageKind.METHOD, is_official=True
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            RequirementPackage.objects.create(
                source="default-cia-5x5",
                version="1.0.0",
                kind=PackageKind.METHOD,
                content={},
            )
