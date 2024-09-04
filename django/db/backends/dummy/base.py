"""
Dummy database backend for Django.

Django uses this if the database ENGINE setting is empty (None or empty string).

Each of these API functions, except connection.close(), raise
ImproperlyConfigured.

Django 的虚拟数据库后端。

如果数据库的 ENGINE 设置为空（None 或空字符串），Django 会使用这个虚拟后端。

除了 connection.close() 之外，这些 API 函数中的每一个都会引发 ImproperlyConfigured 异常。
"""

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.client import BaseDatabaseClient
from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.backends.base.introspection import BaseDatabaseIntrospection
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.dummy.features import DummyDatabaseFeatures


def complain(*args, **kwargs):
    raise ImproperlyConfigured("settings.DATABASES is improperly configured. "
                               "Please supply the ENGINE value. Check "
                               "settings documentation for more details.")


def ignore(*args, **kwargs):
    pass


class DatabaseOperations(BaseDatabaseOperations):
    quote_name = complain


class DatabaseClient(BaseDatabaseClient):
    runshell = complain


class DatabaseCreation(BaseDatabaseCreation):
    create_test_db = ignore
    destroy_test_db = ignore


class DatabaseIntrospection(BaseDatabaseIntrospection):
    get_table_list = complain
    get_table_description = complain
    get_relations = complain
    get_indexes = complain
    get_key_columns = complain


class DatabaseWrapper(BaseDatabaseWrapper):
    operators = {}
    # Override the base class implementations with null
    # implementations. Anything that tries to actually
    # do something raises complain; anything that tries
    # to rollback or undo something raises ignore.
    _cursor = complain
    ensure_connection = complain
    _commit = complain
    _rollback = ignore
    _close = ignore
    _savepoint = ignore
    _savepoint_commit = complain
    _savepoint_rollback = ignore
    _set_autocommit = complain
    # Classes instantiated in __init__().
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DummyDatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations

    def is_usable(self):
        return True
