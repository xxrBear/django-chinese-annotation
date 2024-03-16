import inspect
import os
import warnings
from importlib import import_module

from django.core.exceptions import ImproperlyConfigured
from django.utils.deprecation import RemovedInDjango41Warning
from django.utils.functional import cached_property
from django.utils.module_loading import import_string, module_has_submodule

APPS_MODULE_NAME = 'apps'
MODELS_MODULE_NAME = 'models'


class AppConfig:
    """
    Class representing a Django application and its configuration.

    代表 D 应用程序及其配置的类
    """
    def __init__(self, app_name, app_module):
        # Full Python path to the application e.g. 'django.contrib.admin'.
        # 应用程序的完整Python路径，例如: 'django.contrib.admin'
        self.name = app_name

        # Root module for the application e.g. <module 'django.contrib.admin'
        # from 'django/contrib/admin/__init__.py'>.
        # 应用的根模块，例如: <module 'django.contrib.admin' from 'django/contrib/admin/__init__.py'>.
        self.module = app_module

        # Reference to the Apps registry that holds this AppConfig. Set by the
        # registry when it registers the AppConfig instance.
        # 对保存此AppConfig的应用程序注册表的引用。 由注册中心在注册AppConfig实例时设置
        self.apps = None

        # The following attributes could be defined at the class level in a
        # subclass, hence the test-and-set pattern.
        # 以下属性可以在子类的类级别中定义，因此使用了 test-and-set 模式

        # Last component of the Python path to the application e.g. 'admin'.
        # This value must be unique across a Django project.
        # 到应用程序的Python路径的最后一个组件 'admin'
        # 这个值在 D 项目中必须是唯一的。
        if not hasattr(self, 'label'):
            self.label = app_name.rpartition(".")[2]
        if not self.label.isidentifier():
            raise ImproperlyConfigured(
                "The app label '%s' is not a valid Python identifier." % self.label
            )

        # Human-readable name for the application e.g. "Admin".
        # 应用程序用户友好型名称 例如: "Admin"
        if not hasattr(self, 'verbose_name'):
            self.verbose_name = self.label.title()

        # Filesystem path to the application directory e.g.
        # '/path/to/django/contrib/admin'.
        # 应用程序目录的文件系统路径 例如: '/path/to/django/contrib/admin'
        if not hasattr(self, 'path'):
            self.path = self._path_from_module(app_module)

        # Module containing models e.g. <module 'django.contrib.admin.models'
        # from 'django/contrib/admin/models.py'>. Set by import_models().
        # None if the application doesn't have a models module.
        # 包含模型的模块 例如: <module 'django.contrib.admin.models' from 'django/contrib/admin/models.py'>
        # 由 import_models() 设置。如果应用程序没有 models 模块，则为 None
        self.models_module = None

        # Mapping of lowercase model names to model classes. Initially set to
        # None to prevent accidental access before import_models() runs.
        # 小写模型名到模型类的映射。初始设置为 None，以防止在 import_models() 运行之前意外访问
        self.models = None

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.label)

    @cached_property
    def default_auto_field(self):
        from django.conf import settings
        return settings.DEFAULT_AUTO_FIELD

    @property
    def _is_default_auto_field_overridden(self):
        return self.__class__.default_auto_field is not AppConfig.default_auto_field

    def _path_from_module(self, module):
        """
        Attempt to determine app's filesystem path from its module.

        尝试从其模块确定应用程序的文件系统路径
        """
        # See #21874 for extended discussion of the behavior of this method in
        # various cases.
        # Convert paths to list because Python's _NamespacePath doesn't support
        # indexing.
        # 有关此方法在各种情况下的行为的详细讨论，请参阅#21874
        # 将 paths 转换为 list，因为Python的 _NamespacePath 不支持索引
        paths = list(getattr(module, '__path__', []))
        if len(paths) != 1:
            filename = getattr(module, '__file__', None)
            if filename is not None:
                paths = [os.path.dirname(filename)]
            else:
                # For unknown reasons, sometimes the list returned by __path__
                # contains duplicates that must be removed (#25246).
                # 由于未知的原因，有时 __path__ 返回的列表包含必须删除的重复项(#25246)
                paths = list(set(paths))
        if len(paths) > 1:
            raise ImproperlyConfigured(
                "The app module %r has multiple filesystem locations (%r); "
                "you must configure this app with an AppConfig subclass "
                "with a 'path' class attribute." % (module, paths))
        elif not paths:
            raise ImproperlyConfigured(
                "The app module %r has no filesystem location, "
                "you must configure this app with an AppConfig subclass "
                "with a 'path' class attribute." % module)
        return paths[0]

    @classmethod
    def create(cls, entry):
        """
        Factory that creates an app config from an entry in INSTALLED_APPS.

        从INSTALLED_APPS中的条目创建应用配置的工厂
        """
        # create() eventually returns app_config_class(app_name, app_module).
        app_config_class = None  # AppConfig类
        app_config_name = None
        app_name = None
        app_module = None

        # If import_module succeeds, entry points to the app module.
        # 如果 import_module 成功，入口就指向应用模块。
        try:
            app_module = import_module(entry)
        except Exception:
            pass
        else:
            # If app_module has an apps submodule that defines a single
            # AppConfig subclass, use it automatically.
            # To prevent this, an AppConfig subclass can declare a class
            # variable default = False.
            # If the apps module defines more than one AppConfig subclass,
            # the default one can declare default = True.

            # 如果 app_module 有一个 apps 子模块，它只定义了一个 AppConfig 子类，就自动使用它。
            # 为了防止这种情况，AppConfig 子类可以声明一个类变量 default = False
            # 如果 apps 模块定义了多个 AppConfig 子类，那么默认的一个可以声明 default = True

            if module_has_submodule(app_module, APPS_MODULE_NAME):
                mod_path = '%s.%s' % (entry, APPS_MODULE_NAME)
                mod = import_module(mod_path)
                # Check if there's exactly one AppConfig candidate,
                # excluding those that explicitly define default = False.
                app_configs = [
                    (name, candidate)
                    for name, candidate in inspect.getmembers(mod, inspect.isclass)
                    if (
                        issubclass(candidate, cls) and
                        candidate is not cls and
                        getattr(candidate, 'default', True)
                    )
                ]
                if len(app_configs) == 1:
                    app_config_class = app_configs[0][1]
                    app_config_name = '%s.%s' % (mod_path, app_configs[0][0])
                else:
                    # Check if there's exactly one AppConfig subclass,
                    # among those that explicitly define default = True.
                    app_configs = [
                        (name, candidate)
                        for name, candidate in app_configs
                        if getattr(candidate, 'default', False)
                    ]
                    if len(app_configs) > 1:
                        candidates = [repr(name) for name, _ in app_configs]
                        raise RuntimeError(
                            '%r declares more than one default AppConfig: '
                            '%s.' % (mod_path, ', '.join(candidates))
                        )
                    elif len(app_configs) == 1:
                        app_config_class = app_configs[0][1]
                        app_config_name = '%s.%s' % (mod_path, app_configs[0][0])

            # If app_module specifies a default_app_config, follow the link.
            # default_app_config is deprecated, but still takes over the
            # automatic detection for backwards compatibility during the
            # deprecation period.

            # 如果 app_module 指定了 default_app_config ，请按照链接进行操作。
            # default_app_config 已弃用，但在弃用期间仍将接管向后兼容性的自动检测。

            # -------------------------- 不看了 ----------------------------------------
            try:
                new_entry = app_module.default_app_config
            except AttributeError:
                # Use the default app config class if we didn't find anything.
                if app_config_class is None:
                    app_config_class = cls
                    app_name = entry
            else:
                message = (
                    '%r defines default_app_config = %r. ' % (entry, new_entry)
                )
                if new_entry == app_config_name:
                    message += (
                        'Django now detects this configuration automatically. '
                        'You can remove default_app_config.'
                    )
                else:
                    message += (
                        "However, Django's automatic detection %s. You should "
                        "move the default config class to the apps submodule "
                        "of your application and, if this module defines "
                        "several config classes, mark the default one with "
                        "default = True." % (
                            "picked another configuration, %r" % app_config_name
                            if app_config_name
                            else "did not find this configuration"
                        )
                    )
                warnings.warn(message, RemovedInDjango41Warning, stacklevel=2)
                entry = new_entry
                app_config_class = None
            # --------------------------------------------------------------------------

        # If import_string succeeds, entry is an app config class.
        # 如果 import_string 成功，则 entry 是一个应用配置类。
        if app_config_class is None:
            try:
                app_config_class = import_string(entry)
            except Exception:
                pass
        # If both import_module and import_string failed, it means that entry doesn't have a valid value.
        # 如果 import_module 和 import_string都失败，这意味着 entry 没有有效值 抛出异常
        if app_module is None and app_config_class is None:
            # If the last component of entry starts with an uppercase letter,
            # then it was likely intended to be an app config class; if not,
            # an app module. Provide a nice error message in both cases.
            # 如果条目的最后一个组件以大写字母开头，那么它很可能是一个应用配置类;
            # 如果没有，请使用app模块。在这两种情况下都提供一个漂亮的错误消息
            mod_path, _, cls_name = entry.rpartition('.')
            if mod_path and cls_name[0].isupper():
                # We could simply re-trigger the string import exception, but
                # we're going the extra mile and providing a better error
                # message for typos in INSTALLED_APPS.
                # This may raise ImportError, which is the best exception
                # possible if the module at mod_path cannot be imported.
                # 我们可以简单地重新触发字符串导入异常，但是我们将在 INSTALLED_APPS 中为输入错误提供更好的错误消息。
                # 这可能引发ImportError异常，如果不能导入 mod_path 处的模块，这是可能出现的最佳异常。
                mod = import_module(mod_path)
                candidates = [
                    repr(name)
                    for name, candidate in inspect.getmembers(mod, inspect.isclass)
                    if issubclass(candidate, cls) and candidate is not cls
                ]
                msg = "Module '%s' does not contain a '%s' class." % (mod_path, cls_name)
                if candidates:
                    msg += ' Choices are: %s.' % ', '.join(candidates)
                raise ImportError(msg)
            else:
                # Re-trigger the module import exception.
                import_module(entry)

        # Check for obvious errors. (This check prevents duck typing, but
        # it could be removed if it became a problem in practice.)
        # 检查明显的错误。(这个检查可以防止鸭子输入，但如果它在实践中成为一个问题，可以删除它。)
        if not issubclass(app_config_class, AppConfig):
            raise ImproperlyConfigured(
                "'%s' isn't a subclass of AppConfig." % entry)

        # Obtain app name here rather than in AppClass.__init__ to keep
        # all error checking for entries in INSTALLED_APPS in one place.
        # 在这里获取应用名称，而不是在AppClass.__init__中获取，
        # 以便在一个地方对INSTALLED_APPS中的条目进行所有错误检查。
        if app_name is None:
            try:
                app_name = app_config_class.name
            except AttributeError:
                raise ImproperlyConfigured(
                    "'%s' must supply a name attribute." % entry
                )

        # Ensure app_name points to a valid module.
        # 确保 app_name 指向一个有效的模块
        try:
            app_module = import_module(app_name)
        except ImportError:
            raise ImproperlyConfigured(
                "Cannot import '%s'. Check that '%s.%s.name' is correct." % (
                    app_name,
                    app_config_class.__module__,
                    app_config_class.__qualname__,
                )
            )

        # Entry is a path to an app config class.
        # 入口是一个应用配置类的路径
        return app_config_class(app_name, app_module)

    def get_model(self, model_name, require_ready=True):
        """
        Return the model with the given case-insensitive model_name.

        Raise LookupError if no model exists with this name.

        返回具有给定不区分大小写的 model_name 的模型。
        如果不存在具有此名称的模型，则引发LookupError。
        """
        if require_ready:
            self.apps.check_models_ready()
        else:
            self.apps.check_apps_ready()
        try:
            return self.models[model_name.lower()]
        except KeyError:
            raise LookupError(
                "App '%s' doesn't have a '%s' model." % (self.label, model_name))

    def get_models(self, include_auto_created=False, include_swapped=False):
        """
        Return an iterable of models.

        By default, the following models aren't included:

        - auto-created models for many-to-many relations without
          an explicit intermediate table,
        - models that have been swapped out.

        Set the corresponding keyword argument to True to include such models.
        Keyword arguments aren't documented; they're a private API.

        返回一个模型可迭代对象

        默认情况下，不包括以下模型:

        - 自动为没有显式中间表的多对多关系创建模型，这些模型已经替换出来

        将相应的关键字参数设置为True以包含这样的模型。
        关键字参数没有文档记录;它们是私有 API
        """
        self.apps.check_models_ready()
        for model in self.models.values():
            if model._meta.auto_created and not include_auto_created:
                continue
            if model._meta.swapped and not include_swapped:
                continue
            yield model

    def import_models(self):
        # Dictionary of models for this app, primarily maintained in the
        # 'all_models' attribute of the Apps this AppConfig is attached to.
        # 这个应用的模型字典，主要保存在这个AppConfig所附加的应用的 'all_models' 属性中
        self.models = self.apps.all_models[self.label]

        if module_has_submodule(self.module, MODELS_MODULE_NAME):
            models_module_name = '%s.%s' % (self.name, MODELS_MODULE_NAME)
            self.models_module = import_module(models_module_name)

    def ready(self):
        """
        Override this method in subclasses to run code when Django starts.

        在子类中重写此方法，以便在 D 启动时运行代码
        """
