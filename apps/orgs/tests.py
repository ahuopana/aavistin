from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.products.models import Product

from .models import Organisation, ProductFamily, Role, RoleAssignment, SoDPolicy
from .services import has_role, roles_for_user, visible_organisations


class OrganisationModelTests(TestCase):
    def test_default_sod_policy_is_warn(self):
        org = Organisation.objects.create(name="Acme", slug="acme")
        self.assertEqual(org.sod_policy, SoDPolicy.WARN)


class ProductFamilySoDTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme", sod_policy=SoDPolicy.WARN)

    def test_family_may_tighten_policy(self):
        family = ProductFamily(
            organisation=self.org,
            name="Sensors",
            slug="sensors",
            sod_policy_override=SoDPolicy.ENFORCE,
        )
        family.full_clean()
        family.save()
        self.assertEqual(family.effective_sod_policy, SoDPolicy.ENFORCE)

    def test_family_cannot_loosen_policy(self):
        family = ProductFamily(
            organisation=self.org,
            name="Sensors",
            slug="sensors",
            sod_policy_override=SoDPolicy.OFF,
        )
        with self.assertRaises(ValidationError):
            family.full_clean()

    def test_family_without_override_inherits_org_policy(self):
        family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.assertEqual(family.effective_sod_policy, SoDPolicy.WARN)


class RoleAssignmentConstraintTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.user = User.objects.create_user(username="alice", password="x")

    def test_requires_exactly_one_grantee(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.create(role=Role.VIEWER, organisation=self.org)

    def test_requires_exactly_one_scope(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.create(role=Role.VIEWER, user=self.user)


class RoleResolutionTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.other_family = ProductFamily.objects.create(
            organisation=self.org, name="Actuators", slug="actuators"
        )
        self.user = User.objects.create_user(username="alice", password="x")
        self.group_user = User.objects.create_user(username="bob", password="x")
        self.group = Group.objects.create(name="approvers")
        self.group_user.groups.add(self.group)

    def test_org_level_role_inherited_by_family(self):
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.user, organisation=self.org)
        self.assertTrue(has_role(self.user, Role.VIEWER, product_family=self.family))
        self.assertTrue(has_role(self.user, Role.VIEWER, organisation=self.org))

    def test_family_level_role_not_visible_on_sibling_family(self):
        RoleAssignment.objects.create(
            role=Role.APPROVER, user=self.user, product_family=self.family
        )
        self.assertTrue(has_role(self.user, Role.APPROVER, product_family=self.family))
        self.assertFalse(has_role(self.user, Role.APPROVER, product_family=self.other_family))

    def test_group_role_applies_to_members(self):
        RoleAssignment.objects.create(role=Role.APPROVER, group=self.group, organisation=self.org)
        self.assertIn(Role.APPROVER, roles_for_user(self.group_user, organisation=self.org))
        self.assertNotIn(Role.APPROVER, roles_for_user(self.user, organisation=self.org))

    def test_anonymous_user_has_no_roles(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(roles_for_user(AnonymousUser(), organisation=self.org), set())


class ProductScopeRoleTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.product = Product.objects.create(
            product_family=self.family, name="TempSense", slug="tempsense"
        )
        self.other_product = Product.objects.create(
            product_family=self.family, name="HumSense", slug="humsense"
        )
        self.user = User.objects.create_user(username="alice", password="x")

    def test_org_level_role_inherited_by_product(self):
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.user, organisation=self.org)
        self.assertTrue(has_role(self.user, Role.VIEWER, product=self.product))

    def test_family_level_role_inherited_by_product(self):
        RoleAssignment.objects.create(role=Role.EDITOR, user=self.user, product_family=self.family)
        self.assertTrue(has_role(self.user, Role.EDITOR, product=self.product))

    def test_product_level_role_not_visible_on_sibling_product(self):
        RoleAssignment.objects.create(role=Role.APPROVER, user=self.user, product=self.product)
        self.assertTrue(has_role(self.user, Role.APPROVER, product=self.product))
        self.assertFalse(has_role(self.user, Role.APPROVER, product=self.other_product))

    def test_product_scoped_role_makes_organisation_visible(self):
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.user, product=self.product)
        self.assertEqual(list(visible_organisations(self.user)), [self.org])

    def test_exactly_one_scope_constraint_rejects_two_scopes(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.create(
                role=Role.VIEWER,
                user=self.user,
                organisation=self.org,
                product=self.product,
            )


class VisibleOrganisationsTests(TestCase):
    def test_only_organisations_with_a_role_are_visible(self):
        visible_org = Organisation.objects.create(name="Visible", slug="visible")
        Organisation.objects.create(name="Hidden", slug="hidden")
        user = User.objects.create_user(username="alice", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=user, organisation=visible_org)

        result = visible_organisations(user)
        self.assertEqual(list(result), [visible_org])

    def test_family_scoped_role_makes_organisation_visible(self):
        org = Organisation.objects.create(name="Acme", slug="acme")
        family = ProductFamily.objects.create(organisation=org, name="Sensors", slug="sensors")
        user = User.objects.create_user(username="alice", password="x")
        RoleAssignment.objects.create(role=Role.EDITOR, user=user, product_family=family)

        self.assertEqual(list(visible_organisations(user)), [org])

    def test_superuser_sees_everything(self):
        Organisation.objects.create(name="Acme", slug="acme")
        superuser = User.objects.create_superuser(username="admin", password="x")
        self.assertEqual(visible_organisations(superuser).count(), 1)


class OrganisationViewTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.user = User.objects.create_user(username="alice", password="secret-pass")

    def test_list_requires_login(self):
        response = self.client.get(reverse("orgs:list"))
        self.assertEqual(response.status_code, 302)

    def test_list_shows_only_visible_organisations(self):
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.user, organisation=self.org)
        self.client.force_login(self.user)
        response = self.client.get(reverse("orgs:list"))
        self.assertContains(response, "Acme")

    def test_detail_404s_for_invisible_organisation(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("orgs:detail", args=[self.org.slug]))
        self.assertEqual(response.status_code, 404)


class LdapOffByDefaultTests(TestCase):
    def test_ldap_disabled_by_default(self):
        from django.conf import settings

        self.assertFalse(settings.LDAP_ENABLED)
        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS,
            ["django.contrib.auth.backends.ModelBackend"],
        )
