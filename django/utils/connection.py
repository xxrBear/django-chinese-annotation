from asgiref.local import Local

from django.conf import settings as django_settings
from django.utils.functional import cached_property


class ConnectionProxy:
    """
    Proxy for accessing a connection object's attributes.

    用于访问连接对象属性的代理
    """

    def __init__(self, connections, alias):
        self.__dict__['_connections'] = connections
        self.__dict__['_alias'] = alias

    def __getattr__(self, item):
        return getattr(self._connections[self._alias], item)

    def __setattr__(self, name, value):
        return setattr(self._connections[self._alias], name, value)

    def __delattr__(self, name):
        return delattr(self._connections[self._alias], name)

    def __contains__(self, key):
        return key in self._connections[self._alias]

    def __eq__(self, other):
        return self._connections[self._alias] == other


class ConnectionDoesNotExist(Exception):
    pass


# ------------------------------------------
# 缓存后端 与 数据库后端 共同使用
# ------------------------------------------
class BaseConnectionHandler:
    settings_name = None
    exception_class = ConnectionDoesNotExist
    thread_critical = False

    def __init__(self, settings=None):
        self._settings = settings
        self._connections = Local(self.thread_critical)

    @cached_property
    def settings(self):
        self._settings = self.configure_settings(self._settings)
        return self._settings

    def configure_settings(self, settings):
        # 在 settings 为 None 的时候, 从 settings 文件获取类变量 settings_name 的值
        if settings is None:
            settings = getattr(django_settings, self.settings_name)
        return settings

    def create_connection(self, alias):
        raise NotImplementedError('Subclasses must implement create_connection().')

    def __getitem__(self, alias):
        try:
            return getattr(self._connections, alias)
        except AttributeError:
            if alias not in self.settings:
                raise self.exception_class(f"The connection '{alias}' doesn't exist.")
        conn = self.create_connection(alias)  # settings配置的缓存类
        setattr(self._connections, alias, conn)
        return conn

    def __setitem__(self, key, value):
        print('key: {} value: {}'.format(key, value))
        setattr(self._connections, key, value)

    def __delitem__(self, key):
        delattr(self._connections, key)

    def __iter__(self):
        return iter(self.settings)

    def all(self):
        return [self[alias] for alias in self]
