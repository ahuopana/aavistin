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
        approve_package(
            import_package(
                load_package("common", "1.1.0"), kind=PackageKind.QUESTION_SET, is_official=True
            )
        )
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


def _mfa_package(source: str, **overrides) -> dict:
    content = {
        "source": source,
        "type": "guidance",
        "jurisdiction": "EU",
        "version": "1.0.0",
        "uses": ["common:uses_mfa"],
        "questions": [],
        "scope": {"include": {"var": "uses_mfa"}},
        "fixtures": [
            {"id": "yes", "answers": {"uses_mfa": True}, "expected": {"in_scope": True}},
            {"id": "no", "answers": {"uses_mfa": False}, "expected": {"in_scope": False}},
        ],
    }
    content.update(overrides)
    return content


class SharedQuestionLibraryTests(TestCase):
    def import_common(self):
        package = import_package(
            load_package("common", "1.0.0"), kind=PackageKind.QUESTION_SET, is_official=True
        )
        approve_package(package)
        return package

    def test_common_question_set_passes_lint_and_fixtures(self):
        package = self.import_common()
        self.assertEqual(package.lint_report, [])
        self.assertTrue(all(r["passed"] for r in package.fixture_report))
        self.assertEqual(package.status, PackageStatus.APPROVED)

    def test_common_1_1_question_set_passes_lint_and_fixtures(self):
        self.import_common()
        package = import_package(
            load_package("common", "1.1.0"), kind=PackageKind.QUESTION_SET, is_official=True
        )
        self.assertEqual(package.lint_report, [])
        failed = [r for r in package.fixture_report if not r["passed"]]
        self.assertEqual(failed, [])
        approve_package(package)
        self.assertEqual(package.status, PackageStatus.APPROVED)

    def test_package_can_use_library_question_without_declaring_it(self):
        self.import_common()
        package = import_package(_mfa_package("spec-a"))
        self.assertEqual(package.lint_report, [])
        self.assertEqual(package.status, PackageStatus.FIXTURES_PASSED)

    def test_unknown_library_reference_is_an_error(self):
        self.import_common()
        package = import_package(_mfa_package("spec-a", uses=["common:no_such_question"]))
        codes = {i["code"] for i in package.lint_report}
        self.assertIn("unknown_library_question", codes)

    def test_redeclaring_library_question_warns_and_conflicting_definition_errors(self):
        self.import_common()
        same = {"id": "uses_mfa", "type": "boolean", "level": "software"}
        package = import_package(_mfa_package("spec-a", uses=[], questions=[same]))
        self.assertEqual([i["code"] for i in package.lint_report], ["redeclared_library_question"])

        clash = {"id": "uses_mfa", "type": "boolean", "level": "product"}
        package = import_package(_mfa_package("spec-b", uses=[], questions=[clash]))
        self.assertIn("question_conflict", {i["code"] for i in package.lint_report})

    def test_conflict_with_another_requirement_package_is_an_error(self):
        first = {"id": "has_cloud", "type": "boolean", "level": "software"}
        import_package(
            _mfa_package(
                "spec-a", uses=[], questions=[first], scope={"include": True}, fixtures=[]
            )
        )
        second = {"id": "has_cloud", "type": "number", "level": "software"}
        package = import_package(
            _mfa_package(
                "spec-b", uses=[], questions=[second], scope={"include": True}, fixtures=[]
            )
        )
        self.assertIn("question_conflict", {i["code"] for i in package.lint_report})

    def test_implied_by_cycle_and_duplicate_ids_are_errors(self):
        content = {
            "source": "loop",
            "version": "1.0.0",
            "questions": [
                {
                    "id": "a",
                    "type": "boolean",
                    "level": "software",
                    "implied_by": {"when": {"var": "b"}, "value": True},
                },
                {
                    "id": "b",
                    "type": "boolean",
                    "level": "software",
                    "implied_by": {"when": {"var": "a"}, "value": True},
                },
            ],
        }
        package = import_package(content, kind=PackageKind.QUESTION_SET)
        self.assertIn("implied_by_cycle", {i["code"] for i in package.lint_report})

        self.import_common()
        dup = {
            "source": "other",
            "version": "1.0.0",
            "questions": [{"id": "uses_mfa", "type": "boolean", "level": "software"}],
        }
        package = import_package(dup, kind=PackageKind.QUESTION_SET)
        self.assertIn("duplicate_library_question", {i["code"] for i in package.lint_report})


class DateRuleTests(TestCase):
    """ADR 0018: date questions are ISO strings compared as dates."""

    def test_dates_compare_as_dates(self):
        data = {"placed": "2027-12-11"}
        self.assertTrue(evaluate({">=": [{"var": "placed"}, "2027-12-11"]}, data))
        self.assertFalse(evaluate({"<": [{"var": "placed"}, "2027-12-11"]}, data))

    def test_date_compared_with_number_is_an_error(self):
        with self.assertRaises(RuleEngineError):
            evaluate({">": ["2027-12-11", 3]}, {})

    def test_non_date_string_is_an_error(self):
        with self.assertRaises(RuleEngineError):
            evaluate({">": ["soon", "2027-12-11"]}, {})

    def test_unanswered_date_comparison_is_false(self):
        self.assertFalse(evaluate({">=": [{"var": "placed"}, "2027-12-11"]}, {}))

    def test_years_between_counts_complete_calendar_years(self):
        expr = {"years_between": [{"var": "start"}, {"var": "end"}]}
        self.assertEqual(evaluate(expr, {"start": "2028-03-15", "end": "2033-03-15"}), 5)
        self.assertEqual(evaluate(expr, {"start": "2028-03-15", "end": "2033-03-14"}), 4)
        self.assertEqual(evaluate(expr, {"start": "2028-02-29", "end": "2033-02-28"}), 4)
        self.assertEqual(evaluate(expr, {"start": "2033-03-15", "end": "2028-03-15"}), -5)
        self.assertIsNone(evaluate(expr, {"start": "2028-03-15"}))


def _lint(content):
    base = {"source": "x", "version": "1.0.0", "scope": {"include": True}}
    return lint_package(
        {**base, **content}, is_official=False, existing_packages=RequirementPackage.objects.none()
    )


def _codes(issues):
    return {i["code"] for i in issues}


DATE_Q = {"id": "placed", "type": "date", "level": "software"}
NUM_Q = {"id": "years", "type": "number", "level": "product"}


class ApplicabilityLintTests(TestCase):
    """ADRs 0018 and 0019: typed operator contexts, applies_when, role, dates, fixtures."""

    def test_date_question_allowed_in_comparison_and_years_between(self):
        issues = _lint(
            {
                "questions": [DATE_Q],
                "finding_rules": [
                    {
                        "id": "f",
                        "level": "info",
                        "message": "m",
                        "when": {
                            "and": [
                                {">=": [{"var": "placed"}, "2027-12-11"]},
                                {">": [{"years_between": [{"var": "placed"}, "2030-01-01"]}, 1]},
                            ]
                        },
                    }
                ],
            }
        )
        self.assertNotIn("type_mismatch", _codes(issues))

    def test_date_question_under_arithmetic_is_type_mismatch(self):
        issues = _lint(
            {
                "questions": [DATE_Q],
                "scope": {"include": {">": [{"+": [{"var": "placed"}, 1]}, 2]}},
            }
        )
        self.assertIn("type_mismatch", _codes(issues))

    def test_number_under_years_between_is_type_mismatch(self):
        issues = _lint(
            {
                "questions": [NUM_Q],
                "scope": {
                    "include": {">": [{"years_between": [{"var": "years"}, "2030-01-01"]}, 1]}
                },
            }
        )
        self.assertIn("type_mismatch", _codes(issues))

    def test_applies_when_and_role_are_checked_for_unknown_questions(self):
        issues = _lint(
            {
                "questions": [DATE_Q],
                "role": {"var": "nobody_declares_this"},
                "requirements": [
                    {"id": "r", "roles": ["manufacturer"], "applies_when": {"var": "missing"}}
                ],
            }
        )
        paths = {i["path"] for i in issues if i["code"] == "unknown_question"}
        self.assertIn("role", paths)
        self.assertIn("requirements[0].applies_when", paths)

    def test_classification_vars_allowed_in_applies_when(self):
        issues = _lint(
            {
                "questions": [DATE_Q],
                "classifications": [{"id": "important", "label": "Important"}],
                "requirements": [
                    {
                        "id": "r",
                        "roles": ["manufacturer"],
                        "applies_when": {"var": "class__important"},
                    }
                ],
            }
        )
        self.assertEqual(issues, [])

    def test_requirement_dates_must_be_valid_and_ordered(self):
        issues = _lint(
            {
                "questions": [DATE_Q],
                "requirements": [
                    {"id": "a", "roles": ["manufacturer"], "applies_from": "2027-13-01"},
                    {
                        "id": "b",
                        "roles": ["manufacturer"],
                        "applies_from": "2028-01-01",
                        "applies_until": "2027-01-01",
                    },
                ],
            }
        )
        self.assertIn("bad_date", _codes(issues))
        self.assertIn("date_order", _codes(issues))

    def test_fixture_expecting_requirements_needs_as_of(self):
        issues = _lint(
            {
                "questions": [DATE_Q],
                "fixtures": [{"id": "f", "answers": {}, "expected": {"requirements": []}}],
            }
        )
        self.assertIn("fixture_needs_as_of", _codes(issues))


APPLICABILITY_PACKAGE = {
    "source": "demo-applicability",
    "version": "1",
    "questions": [
        {"id": "placed", "type": "date", "level": "software"},
        {
            "id": "operator_role",
            "type": "choice",
            "level": "product",
            "choices": ["manufacturer", "importer"],
        },
        {"id": "own_brand", "type": "boolean", "level": "product"},
        {"id": "critical", "type": "boolean", "level": "product"},
    ],
    "scope": {"include": True},
    "role": {"if": [{"var": "own_brand"}, "manufacturer", {"var": "operator_role"}]},
    "classifications": [{"id": "critical", "label": "Critical", "when": {"var": "critical"}}],
    "requirements": [
        {"id": "always", "roles": ["manufacturer", "importer"]},
        {"id": "manufacturer_only", "roles": ["manufacturer"]},
        {"id": "importer_only", "roles": ["importer"]},
        {
            "id": "placed_after_cut_off",
            "roles": ["manufacturer"],
            "applies_when": {">=": [{"var": "placed"}, "2027-12-11"]},
        },
        {"id": "reporting", "roles": ["manufacturer"], "applies_from": "2026-09-11"},
        {"id": "transitional", "roles": ["manufacturer"], "applies_until": "2028-06-11"},
        {
            "id": "critical_only",
            "roles": ["manufacturer"],
            "applies_when": {"var": "class__critical"},
        },
    ],
    "assessment_routes": [
        {"id": "self", "label": "Self", "allowed_when": {"!": {"var": "class__critical"}}},
        {"id": "third_party", "label": "Third party"},
    ],
}


class ApplicabilityEvaluationTests(TestCase):
    """ADR 0019, through the shared evaluator used by fixtures and assessments."""

    def evaluate(self, answers, as_of=None):
        from datetime import date

        from .evaluator import evaluate_package

        return evaluate_package(
            APPLICABILITY_PACKAGE, answers, as_of=date.fromisoformat(as_of) if as_of else None
        )

    def test_unknown_role_hides_nothing(self):
        result = self.evaluate({"placed": "2028-01-01"})
        self.assertIsNone(result["role"])
        self.assertIn("importer_only", result["requirements"])
        self.assertIn("manufacturer_only", result["requirements"])

    def test_role_filters_requirements(self):
        result = self.evaluate({"operator_role": "importer"})
        self.assertEqual(result["role"], "importer")
        self.assertEqual(result["requirements"], ["always", "importer_only"])

    def test_role_expression_can_override_the_answer(self):
        result = self.evaluate({"operator_role": "importer", "own_brand": True})
        self.assertEqual(result["role"], "manufacturer")
        self.assertNotIn("importer_only", result["requirements"])

    def test_placement_rule_lives_in_applies_when(self):
        before = self.evaluate({"operator_role": "manufacturer", "placed": "2027-06-01"})
        after = self.evaluate({"operator_role": "manufacturer", "placed": "2028-01-01"})
        self.assertNotIn("placed_after_cut_off", before["requirements"])
        self.assertIn("placed_after_cut_off", after["requirements"])

    def test_calendar_dates_compare_with_the_assessment_date(self):
        early = self.evaluate({"operator_role": "manufacturer"}, as_of="2026-01-01")
        self.assertNotIn("reporting", early["requirements"])
        self.assertEqual(
            early["upcoming_requirements"], [{"id": "reporting", "applies_from": "2026-09-11"}]
        )
        later = self.evaluate({"operator_role": "manufacturer"}, as_of="2028-06-11")
        self.assertIn("reporting", later["requirements"])
        self.assertEqual(
            later["ended_requirements"], [{"id": "transitional", "applies_until": "2028-06-11"}]
        )

    def test_classification_drives_applies_when_and_routes(self):
        result = self.evaluate({"operator_role": "manufacturer", "critical": True})
        self.assertIn("critical_only", result["requirements"])
        self.assertEqual(result["assessment_routes"], ["third_party"])

    def test_fixture_runner_checks_classifications_routes_and_requirements(self):
        content = {
            **APPLICABILITY_PACKAGE,
            "fixtures": [
                {
                    "id": "passes",
                    "as_of": "2027-01-01",
                    "answers": {"operator_role": "importer", "critical": True},
                    "expected": {
                        "classifications": ["critical"],
                        "assessment_routes": ["third_party"],
                        "requirements": ["always", "importer_only"],
                    },
                },
                {
                    "id": "fails",
                    "as_of": "2027-01-01",
                    "answers": {"operator_role": "importer"},
                    "expected": {"assessment_routes": ["third_party"]},
                },
            ],
        }
        reports = {r["id"]: r for r in run_fixtures(content)}
        self.assertTrue(reports["passes"]["passed"], reports["passes"]["errors"])
        self.assertFalse(reports["fails"]["passed"])
        self.assertIn("assessment_routes", reports["fails"]["errors"][0])
