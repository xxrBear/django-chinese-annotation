"""
Invokes django-admin when the django module is run as a script.

Example: python -m django check

当django模块作为脚本运行时调用django-admin
"""
from django.core import management

if __name__ == "__main__":
    management.execute_from_command_line()
