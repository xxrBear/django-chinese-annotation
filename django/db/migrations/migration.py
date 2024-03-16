from django.db.migrations import operations
from django.db.migrations.utils import get_migration_name_timestamp
from django.db.transaction import atomic

from .exceptions import IrreversibleError


class Migration:
    """
    The base class for all migrations.

    Migration files will import this from django.db.migrations.Migration
    and subclass it as a class called Migration. It will have one or more
    of the following attributes:

     - operations: A list of Operation instances, probably from django.db.migrations.operations
     - dependencies: A list of tuples of (app_path, migration_name)
     - run_before: A list of tuples of (app_path, migration_name)
     - replaces: A list of migration_names

    Note that all migrations come out of migrations and into the Loader or
    Graph as instances, having been initialized with their app label and name.

    所有迁移的基类。
    迁移文件将从 django.db.migrations.Migration 中导入它，并将其子类化为 Migration 类。
    它将具有以下 一个或多个属性:

    - operations:   Operation实例列表，可能来自 django.db.migrations.operations
    - dependencies: (app_path, migration_name) 的元组列表
    - run_before:   (app_path, migration_name) 的元组列表
    - replaces:     迁移名称列表

    请注意，所有迁移都是从迁移中出来的，并作为实例进入Loader或Graph，并使用它们的应用程序标签和名称进行初始化。
    """

    # Operations to apply during this migration, in order.
    # 在此迁移期间应用的操作，按顺序排列。
    operations = []

    # Other migrations that should be run before this migration.
    # Should be a list of (app, migration_name).
    # 在此迁移之前应该运行的其他迁移。需要是 (app, migration_name) 的列表
    dependencies = []

    # Other migrations that should be run after this one (i.e. have
    # this migration added to their dependencies). Useful to make third-party
    # apps' migrations run after your AUTH_USER replacement, for example.
    # 应该在此迁移之后运行的其他迁移(即将此迁移添加到其依赖项中)。例如，用于在替换AUTH_USER后运行第三方应用程序的迁移。
    run_before = []

    # Migration names in this app that this migration replaces. If this is
    # non-empty, this migration will only be applied if all these migrations
    # are not applied.
    # 此迁移所替换的应用程序中的迁移名称。如果它不为空，则只有在不应用所有这些迁移时才会应用此迁移。
    replaces = []

    # Is this an initial migration? Initial migrations are skipped on
    # --fake-initial if the table or fields already exist. If None, check if
    # the migration has any dependencies to determine if there are dependencies
    # to tell if db introspection needs to be done. If True, always perform
    # introspection. If False, never perform introspection.
    # 这是初始迁移吗?如果表或字段已经存在，则跳过初始迁移 --fake-initial参数
    # 如果None，检查迁移是否有任何依赖项，以确定是否有依赖项来判断是否需要进行db自省。
    # 如果为True，则始终执行自省。如果为False，永远不要执行自省。
    initial = None

    # Whether to wrap the whole migration in a transaction. Only has an effect
    # on database backends which support transactional DDL.
    # 是否将整个迁移包装在事务中。只对支持事务性DDL的数据库后端有影响。
    atomic = True

    def __init__(self, name, app_label):
        self.name = name
        self.app_label = app_label
        # Copy dependencies & other attrs as we might mutate them at runtime
        self.operations = list(self.__class__.operations)
        self.dependencies = list(self.__class__.dependencies)
        self.run_before = list(self.__class__.run_before)
        self.replaces = list(self.__class__.replaces)

    def __eq__(self, other):
        return (
            isinstance(other, Migration) and
            self.name == other.name and
            self.app_label == other.app_label
        )

    def __repr__(self):
        return "<Migration %s.%s>" % (self.app_label, self.name)

    def __str__(self):
        return "%s.%s" % (self.app_label, self.name)

    def __hash__(self):
        return hash("%s.%s" % (self.app_label, self.name))

    def mutate_state(self, project_state, preserve=True):
        """
        Take a ProjectState and return a new one with the migration's
        operations applied to it. Preserve the original object state by
        default and return a mutated state from a copy.

        获取一个 ProjectState，并返回一个新的，其中包含应用于它的迁移操作。
        默认情况下保留原始对象状态，并从副本返回一个变异的状态。
        """
        new_state = project_state
        if preserve:
            new_state = project_state.clone()

        for operation in self.operations:
            operation.state_forwards(self.app_label, new_state)
        return new_state

    def apply(self, project_state, schema_editor, collect_sql=False):
        """
        Take a project_state representing all migrations prior to this one
        and a schema_editor for a live database and apply the migration
        in a forwards order.

        Return the resulting project state for efficient reuse by following
        Migrations.

        取一个表示在此之前的所有迁移的project_state和一个用于活动数据库的schema_editor，并以向前的顺序应用迁移。
        返回结果项目状态，以便通过遵循迁移进行有效重用。
        """
        for operation in self.operations:
            # If this operation cannot be represented as SQL, place a comment
            # there instead
            if collect_sql:
                schema_editor.collected_sql.append("--")
                if not operation.reduces_to_sql:
                    schema_editor.collected_sql.append(
                        "-- MIGRATION NOW PERFORMS OPERATION THAT CANNOT BE WRITTEN AS SQL:"
                    )
                schema_editor.collected_sql.append("-- %s" % operation.describe())
                schema_editor.collected_sql.append("--")
                if not operation.reduces_to_sql:
                    continue
            # Save the state before the operation has run
            old_state = project_state.clone()
            operation.state_forwards(self.app_label, project_state)
            # Run the operation
            atomic_operation = operation.atomic or (self.atomic and operation.atomic is not False)
            if not schema_editor.atomic_migration and atomic_operation:
                # Force a transaction on a non-transactional-DDL backend or an
                # atomic operation inside a non-atomic migration.
                with atomic(schema_editor.connection.alias):
                    operation.database_forwards(self.app_label, schema_editor, old_state, project_state)
            else:
                # Normal behaviour
                operation.database_forwards(self.app_label, schema_editor, old_state, project_state)
        return project_state

    def unapply(self, project_state, schema_editor, collect_sql=False):
        """
        Take a project_state representing all migrations prior to this one
        and a schema_editor for a live database and apply the migration
        in a reverse order.

        The backwards migration process consists of two phases:

        1. The intermediate states from right before the first until right
           after the last operation inside this migration are preserved.
        2. The operations are applied in reverse order using the states
           recorded in step 1.

        取一个表示在此之前的所有迁移的project_state和一个用于活动数据库的schema_editor，并以相反的顺序应用迁移。

        向后迁移过程包括两个阶段:
        1. 在此迁移中，从第一个操作之前到最后一个操作之后的中间状态将被保留。
        2. 使用步骤1中记录的状态以相反的顺序应用这些操作。
        """
        # Construct all the intermediate states we need for a reverse migration
        to_run = []
        new_state = project_state
        # Phase 1
        for operation in self.operations:
            # If it's irreversible, error out
            if not operation.reversible:
                raise IrreversibleError("Operation %s in %s is not reversible" % (operation, self))
            # Preserve new state from previous run to not tamper the same state
            # over all operations
            new_state = new_state.clone()
            old_state = new_state.clone()
            operation.state_forwards(self.app_label, new_state)
            to_run.insert(0, (operation, old_state, new_state))

        # Phase 2
        for operation, to_state, from_state in to_run:
            if collect_sql:
                schema_editor.collected_sql.append("--")
                if not operation.reduces_to_sql:
                    schema_editor.collected_sql.append(
                        "-- MIGRATION NOW PERFORMS OPERATION THAT CANNOT BE WRITTEN AS SQL:"
                    )
                schema_editor.collected_sql.append("-- %s" % operation.describe())
                schema_editor.collected_sql.append("--")
                if not operation.reduces_to_sql:
                    continue
            atomic_operation = operation.atomic or (self.atomic and operation.atomic is not False)
            if not schema_editor.atomic_migration and atomic_operation:
                # Force a transaction on a non-transactional-DDL backend or an
                # atomic operation inside a non-atomic migration.
                with atomic(schema_editor.connection.alias):
                    operation.database_backwards(self.app_label, schema_editor, from_state, to_state)
            else:
                # Normal behaviour
                operation.database_backwards(self.app_label, schema_editor, from_state, to_state)
        return project_state

    def suggest_name(self):
        """
        Suggest a name for the operations this migration might represent. Names
        are not guaranteed to be unique, but put some effort into the fallback
        name to avoid VCS conflicts if possible.

        建议此迁移可能表示的操作的名称。
        名称不能保证是唯一的，但是如果可能的话，在备用名称上做一些努力以避免VCS冲突。
        """
        name = None
        if len(self.operations) == 1:
            name = self.operations[0].migration_name_fragment
        elif (
            len(self.operations) > 1 and
            all(isinstance(o, operations.CreateModel) for o in self.operations)
        ):
            name = '_'.join(sorted(o.migration_name_fragment for o in self.operations))
        if name is None:
            name = 'initial' if self.initial else 'auto_%s' % get_migration_name_timestamp()
        return name


class SwappableTuple(tuple):
    """
    Subclass of tuple so Django can tell this was originally a swappable
    dependency when it reads the migration file.
    """

    def __new__(cls, value, setting):
        self = tuple.__new__(cls, value)
        self.setting = setting
        return self


def swappable_dependency(value):
    """Turn a setting value into a dependency."""
    return SwappableTuple((value.split(".", 1)[0], "__first__"), value)
