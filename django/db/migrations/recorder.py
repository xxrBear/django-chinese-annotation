from django.apps.registry import Apps
from django.db import DatabaseError, models
from django.utils.functional import classproperty
from django.utils.timezone import now

from .exceptions import MigrationSchemaMissing


class MigrationRecorder:
    """
    Deal with storing migration records in the database.

    Because this table is actually itself used for dealing with model
    creation, it's the one thing we can't do normally via migrations.
    We manually handle table creation/schema updating (using schema backend)
    and then have a floating model to do queries with.

    If a migration is unapplied its row is removed from the table. Having
    a row in the table always means a migration is applied.

    处理在数据库中存储迁移记录。

    因为这个表本身实际上是用来处理模型创建的，所以它是我们通过迁移通常不能做的一件事。
    我们手动处理表创建/模式更新(使用模式后端)，然后有一个浮动模型来执行查询。

    如果未应用迁移，则从表中删除其行。表中有一行总是意味着应用了迁移。

    """
    _migration_class = None

    @classproperty
    def Migration(cls):
        """
        Lazy load to avoid AppRegistryNotReady if installed apps import
        MigrationRecorder.

        只是一个Migration模型对象!
        """
        if cls._migration_class is None:
            class Migration(models.Model):
                app = models.CharField(max_length=255)
                name = models.CharField(max_length=255)
                applied = models.DateTimeField(default=now)

                class Meta:
                    apps = Apps()
                    app_label = 'migrations'
                    db_table = 'django_migrations'

                def __str__(self):
                    return 'Migration %s for %s' % (self.name, self.app)

            cls._migration_class = Migration
        return cls._migration_class

    def __init__(self, connection):
        self.connection = connection

    @property
    def migration_qs(self):
        # 查询django_migrations表的数据
        return self.Migration.objects.using(self.connection.alias)

    def has_table(self):
        """Return True if the django_migrations table exists."""
        # 检查django_migrations表是否存在
        with self.connection.cursor() as cursor:
            tables = self.connection.introspection.table_names(cursor)
        return self.Migration._meta.db_table in tables

    def ensure_schema(self):
        """
        Ensure the table exists and has the correct schema.

        确保django_migrations表存在!
        """
        # If the table's there, that's fine - we've never changed its schema
        # in the codebase.
        if self.has_table():
            return
        # Make the table
        try:
            with self.connection.schema_editor() as editor:
                editor.create_model(self.Migration)
        except DatabaseError as exc:
            raise MigrationSchemaMissing("Unable to create the django_migrations table (%s)" % exc)

    def applied_migrations(self):
        """
        Return a dict mapping (app_name, migration_name) to Migration instances
        for all applied migrations.
        """
        if self.has_table():
            return {(migration.app, migration.name): migration for migration in self.migration_qs}
        else:
            # If the django_migrations table doesn't exist, then no migrations
            # are applied.
            return {}

    def record_applied(self, app, name):
        """
        Record that a migration was applied.

        django_migrations表中添加一条记录
        """
        self.ensure_schema()
        self.migration_qs.create(app=app, name=name)

    def record_unapplied(self, app, name):
        """
        Record that a migration was unapplied.

        django_migrations表中删除记录!
        """
        self.ensure_schema()
        self.migration_qs.filter(app=app, name=name).delete()

    def flush(self):
        """
        Delete all migration records. Useful for testing migrations.

        django_migrations表中删除所有记录! 一般用于测试
        """
        self.migration_qs.all().delete()
