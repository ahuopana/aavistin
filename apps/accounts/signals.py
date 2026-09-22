from django_auth_ldap.backend import populate_user

from .models import AuthSource


def set_ldap_auth_source(sender, user, ldap_user, **kwargs):
    user.auth_source = AuthSource.LDAP


populate_user.connect(set_ldap_auth_source, dispatch_uid="accounts.set_ldap_auth_source")
