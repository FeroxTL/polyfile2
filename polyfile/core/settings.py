import importlib.util
import os
import sys
from pathlib import Path

from django.urls import reverse_lazy
from environ import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

env = environ.Env(
    DEBUG=(bool, 'runserver' in sys.argv),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
    INTERNAL_IPS=(list, ['127.0.0.1']),
)
ENV_FILE = Path(os.environ.get("POLYFILE_ENV_FILE", Path.cwd() / ".env")).expanduser()
environ.Env.read_env(ENV_FILE)

# Runtime data (database, collected static, media) must not live inside the package:
# a wheel is installed into site-packages, which may be read-only and is replaced on upgrade.
DATA_DIR = Path(env.str("POLYFILE_DATA_DIR", str(Path.cwd()))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# MkDocs output is built into the package and shipped with distributions.
DOCS_DIR = BASE_DIR / "docs"

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str('SECRET_KEY', 'django-insecure-o_d=g9_#sofs^h8p34x5!$$gkdlqtk_2@-#0kw%gx2off@13&!')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DEBUG')
TESTING = "test" in sys.argv or "PYTEST_VERSION" in os.environ
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

LOGIN_URL = reverse_lazy('accounts-login')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'webpack_loader',

    'polyfile.core',
    'polyfile.apps.accounts',
    'polyfile.apps.storage',
    'polyfile.apps.share',
    'polyfile.contrib.backends',
]


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.debug',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTH_USER_MODEL = 'accounts.User'
ROOT_URLCONF = 'polyfile.core.urls'
WSGI_APPLICATION = 'polyfile.core.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': env.db_url(
        'DATABASE_URL',
        default=f'sqlite:///{DATA_DIR / "db.sqlite3"}'
    )
}


# Webpack loader
# Prefer development assets only when they exist; otherwise fall back to the production
# bundle shipped with the package. This works both in a source checkout and in a wheel.
DEV_WEBPACK_STATS_FILE = ROOT_DIR / 'webpack-dev-stats.json'
DEV_WEBPACK_ASSETS_DIR = ROOT_DIR / 'web_dev_assets'
PROD_WEBPACK_STATS_FILE = BASE_DIR / 'webpack-stats.json'
PROD_WEBPACK_ASSETS_DIR = BASE_DIR / 'web_assets'

DEFAULT_WEBPACK_STATS_FILE = (
    DEV_WEBPACK_STATS_FILE
    if DEBUG and DEV_WEBPACK_STATS_FILE.exists()
    else PROD_WEBPACK_STATS_FILE
)
DEFAULT_WEBPACK_ASSETS_DIR = (
    DEV_WEBPACK_ASSETS_DIR
    if DEBUG and DEV_WEBPACK_ASSETS_DIR.exists()
    else PROD_WEBPACK_ASSETS_DIR
)

WEBPACK_LOADER = {
    'DEFAULT': {
        'BUNDLE_DIR_NAME': 'bundles/',
        'STATS_FILE': env.str(
            'WEBPACK_STATS_FILE',
            str(DEFAULT_WEBPACK_STATS_FILE),
        ),
        'POLL_INTERVAL': 0.3,
        'IGNORE': [r'.+\.hot-update.js', r'.+\.map'],
        'TIMEOUT': 30,
    }
}
WEBPACK_ASSETS_DIR = env.str(
    'WEBPACK_ASSETS_DIR',
    str(DEFAULT_WEBPACK_ASSETS_DIR),
)


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = Path(env.str('STATIC_ROOT', str(DATA_DIR / 'static')))

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = Path(env.str('MEDIA_ROOT', str(DATA_DIR / 'media')))
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
STATICFILES_DIRS = tuple(
    path for path in (WEBPACK_ASSETS_DIR,) if Path(path).exists()
)

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Debug toolbar
DEBUG_TOOLBAR_ENABLED = env.bool(
    'DEBUG_TOOLBAR_ENABLED',
    DEBUG and importlib.util.find_spec("debug_toolbar") is not None,
)
if DEBUG_TOOLBAR_ENABLED:
    INSTALLED_APPS.append('debug_toolbar')
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    INTERNAL_IPS = [
        "127.0.0.1",
    ]
