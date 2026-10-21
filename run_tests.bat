@echo off
set DJANGO_SETTINGS_MODULE=config.settings.development
py manage.py test %* 2>&1
