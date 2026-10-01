"""Authentication — abstract provider + registry for case-repo implementations."""

from zframe.auth.base import AuthProvider, NoAuth
from zframe.auth.factory import build_auth, register_auth, registered_auth_types

__all__ = [
    "AuthProvider",
    "NoAuth",
    "build_auth",
    "register_auth",
    "registered_auth_types",
]
