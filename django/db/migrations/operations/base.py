from django.db import router


class Operation:
    """
    Base class for migration operations.

    It's responsible for both mutating the in-memory model state
    (see db/migrations/state.py) to represent what it performs, as well
    as actually performing it against a live database.

    Note that some operations won't modify memory state at all (e.g. data
    copying operations), and some will need their modifications to be
    optionally specified by the user (e.g. custom Python code snippets)

    Due to the way this class deals with deconstruction, it should be
    considered immutable.

    迁移操作的基类。

    它既负责改变内存中的模型状态(请参阅db/migrations/state.py)以表示它所执行的操作，也负责对实时数据库实际执行操作。

    请注意，有些操作根本不会修改内存状态(例如数据复制操作)，有些操作需要用户选择性地指定其修改(例如自定义Python代码段)。

    由于该类处理解构的方式，它应该被认为是不可变的。
    """

    # If this migration can be run in reverse.
    # Some operations are impossible to reverse, like deleting data.
    reversible = True  # 可逆

    # Can this migration be represented as SQL? (things like RunPython cannot)
    reduces_to_sql = True

    # Should this operation be forced as atomic even on backends with no
    # DDL transaction support (i.e., does it have no DDL, like RunPython)
    atomic = False

    # Should this operation be considered safe to elide and optimize across?
    elidable = False

    serialization_expand_args = []

    def __new__(cls, *args, **kwargs):
        # We capture the arguments to make returning them trivial
        self = object.__new__(cls)
        self._constructor_args = (args, kwargs)
        return self

    def deconstruct(self):  # 解构；拆析
        """
        Return a 3-tuple of class import path (or just name if it lives
        under django.db.migrations), positional arguments, and keyword
        arguments.
        """
        return (
            self.__class__.__name__,
            self._constructor_args[0],
            self._constructor_args[1],
        )

    def state_forwards(self, app_label, state):
        """
        Take the state from the previous migration, and mutate it
        so that it matches what this migration would perform.

        从以前的迁移中获取状态，并对其进行修改，使其与这次迁移将执行的操作相匹配。
        """
        raise NotImplementedError('subclasses of Operation must provide a state_forwards() method')

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        """
        Perform the mutation on the database schema in the normal
        (forwards) direction.

        在正常(向前)方向上对数据库模式执行突变。
        """
        raise NotImplementedError('subclasses of Operation must provide a database_forwards() method')

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        """
        Perform the mutation on the database schema in the reverse
        direction - e.g. if this were CreateModel, it would in fact
        drop the model's table.

        以相反的方向对数据库模式执行突变 —— 例如，如果这是CreateModel，它实际上会删除模型的表。
        """
        raise NotImplementedError('subclasses of Operation must provide a database_backwards() method')

    def describe(self):
        """
        Output a brief summary of what the action does.

        输出操作操作的简要摘要。
        """
        return "%s: %s" % (self.__class__.__name__, self._constructor_args)

    @property
    def migration_name_fragment(self):
        """
        A filename part suitable for automatically naming a migration
        containing this operation, or None if not applicable.

        适合于自动命名包含此操作的迁移的文件名部分，如果不适用则为None。
        """
        return None

    def references_model(self, name, app_label):
        """
        Return True if there is a chance this operation references the given
        model name (as a string), with an app label for accuracy.

        Used for optimization. If in doubt, return True;
        returning a false positive will merely make the optimizer a little
        less efficient, while returning a false negative may result in an
        unusable optimized migration.
        """
        return True

    def references_field(self, model_name, name, app_label):
        """
        Return True if there is a chance this operation references the given
        field name, with an app label for accuracy.

        Used for optimization. If in doubt, return True.
        """
        return self.references_model(model_name, app_label)

    def allow_migrate_model(self, connection_alias, model):
        """
        Return whether or not a model may be migrated.

        This is a thin wrapper around router.allow_migrate_model() that
        preemptively rejects any proxy, swapped out, or unmanaged model.
        """
        if not model._meta.can_migrate(connection_alias):
            return False

        return router.allow_migrate_model(connection_alias, model)

    def reduce(self, operation, app_label):
        """
        Return either a list of operations the actual operation should be
        replaced with or a boolean that indicates whether or not the specified
        operation can be optimized across.
        """
        if self.elidable:
            return [operation]
        elif operation.elidable:
            return [self]
        return False

    def __repr__(self):
        return "<%s %s%s>" % (
            self.__class__.__name__,
            ", ".join(map(repr, self._constructor_args[0])),
            ",".join(" %s=%r" % x for x in self._constructor_args[1].items()),
        )
