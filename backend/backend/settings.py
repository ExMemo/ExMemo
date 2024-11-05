"""
Django settings for backend project.

Generated by 'django-admin startproject' using Django 4.2.7.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent  # /opt/exmemo/backend/
BASE_DATA_DIR = os.path.join(BASE_DIR, "data")

if BASE_DIR not in os.sys.path:
    os.sys.path.append(BASE_DIR)

env_path = os.path.join(BASE_DIR, ".env")
load_dotenv(env_path)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-u$(fykhsmm7$#q*w57h75#0_6j3=12n*^gr!a(18we14pc2+7r"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_cron",
    # add
    "app_dataforge",
    "app_diet",
    "app_translate",
    "app_sync",
    "app_message",
    "app_web",
    "app_record",
    "app_bm_syncex",
    "backend.common.user",
    "rest_framework",
    "corsheaders",
    "knox",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # this should be before CommonMiddleware
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# add by wanglei

BACKEND_PORT_OUTER = os.getenv("BACKEND_PORT_OUTER", "8005")
BACKEND_ADDR_OUTER = os.getenv("BACKEND_ADDR_OUTER", "localhost")
CORS_ALLOWED_ORIGINS = [
    "chrome-extension://egfnajgieeffieaboibcmmjjbjcifbpn",
    "app://obsidian.md",
    f"http://{BACKEND_ADDR_OUTER}:{BACKEND_PORT_OUTER}",  # Use external ports
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

CRON_CLASSES = [
    "backend.common.files.filecache.ClearCacheCronJob",
]

WSGI_APPLICATION = "backend.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "exmemo",
        "USER": "postgres",
        "PASSWORD": os.getenv("PGSQL_PASSWORD", "123456"),
        "HOST": os.getenv("PGSQL_HOST", "localhost"),
        "PORT": os.getenv("PGSQL_PORT", "5432"),
        "TEST": {
            "MIGRATE": True,  # Run migrations
        },
    },
    "postgres": {  # to create default database
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": "postgres",
        "PASSWORD": os.getenv("PGSQL_PASSWORD", "123456"),
        "HOST": os.getenv("PGSQL_HOST", "localhost"),
        "PORT": os.getenv("PGSQL_PORT", "5432"),
    },
}

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en-US")

TIME_ZONE = "UTC"
USE_I18N = True

LANGUAGES = [
    ("en", "English"),
    ("zh", "Chinese"),
]

LOCALE_PATHS = [
    os.path.join(BASE_DIR, "locale"),
]


USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/


static_dir = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

STATIC_URL = "static/"
STATICFILES_DIRS = [os.path.join(static_dir)]


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# xieyan
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

MEDIA_URL = "/media/"
MEDIA_ROOT = "/tmp/"
MEDIA_FILE_DIR = "files"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ("knox.auth.TokenAuthentication",),
}

REST_KNOX = {
    "TOKEN_TTL": timedelta(hours=72),
    "AUTO_REFRESH": False,
}

# TIME_ZONE = 'America/New_York'
TIME_ZONE = "Asia/Shanghai"
USE_TZ = True

import backend.common.files.filecache as filecache

filecache.init(os.path.join(MEDIA_ROOT, MEDIA_FILE_DIR))

from django.db import connection
from django.db import connections
from django.db.utils import OperationalError

db_conn = connections["default"]
try:
    db_conn.cursor()
except OperationalError:
    db_conn = connections["postgres"]
    cursor = db_conn.cursor()
    cursor.execute("CREATE DATABASE exmemo")

with connection.cursor() as cursor:  # for test db
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

import sys
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="DEBUG")  # xieyan debug
