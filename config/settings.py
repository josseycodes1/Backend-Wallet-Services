import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import structlog
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# ========== LEAPCELL SPECIFIC SETTINGS ==========
# Site URL for production - IMPORTANT!
SITE_URL = os.getenv('SITE_URL', 'http://localhost:8001')
BASE_URL = SITE_URL

# Allowed hosts - Add Leapcell domains
DEFAULT_ALLOWED_HOSTS = 'localhost,127.0.0.1'
ADDITIONAL_HOSTS = os.getenv('ADDITIONAL_HOSTS', '')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', DEFAULT_ALLOWED_HOSTS).split(',')
if ADDITIONAL_HOSTS:
    ALLOWED_HOSTS += ADDITIONAL_HOSTS.split(',')

# Add Leapcell default domains
ALLOWED_HOSTS += [
    '.leapcell.dev',
    '.leapcell.app',
    '.leapcell.run',
]

# CORS settings - Update for production
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:8001,http://127.0.0.1:8000').split(',')

# In production, disable CORS_ALLOW_ALL_ORIGINS for security
CORS_ALLOW_ALL_ORIGINS = DEBUG

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_yasg',
    'corsheaders',
    
    # Local apps
    'users',
    'wallet',
    'api_keys',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api_keys.middleware.APIKeyMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ========== DATABASE CONFIGURATION ==========
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=not DEBUG
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
            'NAME': os.getenv('DB_NAME', BASE_DIR / 'db.sqlite3'),
            'USER': os.getenv('DB_USER', ''),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', ''),
            'PORT': os.getenv('DB_PORT', ''),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ========== STATIC FILES CONFIGURATION ==========
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'api_keys.authentication.APIKeyAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '1000/day',
    }
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_EXPIRATION_DELTA', 7))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ALGORITHM': os.getenv('JWT_ALGORITHM', 'HS256'),
    'SIGNING_KEY': SECRET_KEY,
}

# ========== EXTERNAL SERVICES ==========
# Paystack
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
PAYSTACK_WEBHOOK_SECRET = os.getenv('PAYSTACK_WEBHOOK_SECRET')

# API Key Settings
API_KEY_PREFIX = os.getenv('API_KEY_PREFIX', 'sk_live_')
API_KEY_LENGTH = int(os.getenv('API_KEY_LENGTH', 32))
MAX_API_KEYS_PER_USER = int(os.getenv('MAX_API_KEYS_PER_USER', 5))

# Google OAuth - Auto-generate redirect URI based on SITE_URL
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
    'GOOGLE_OAUTH_REDIRECT_URI', 
    f"{SITE_URL}/auth/google/callback/"
)

# ========== SECURITY SETTINGS FOR PRODUCTION ==========
if not DEBUG:
    # Security headers
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Trust the leapcell proxy
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
    USE_X_FORWARDED_PORT = True

# ========== LOGGING CONFIGURATION ==========
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# REMOVE OR COMMENT OUT THIS LINE (it's trying to create logs directory)
# os.makedirs(BASE_DIR / 'logs', exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console_formatter': {
            '()': structlog.stdlib.ProcessorFormatter,
            'processor': structlog.processors.KeyValueRenderer(
                key_order=['timestamp', 'level', 'event', 'logger']
            ),
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console_formatter',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'users': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'wallet': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'transactions': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'api_keys': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        # Add drf_yasg logger to see Swagger errors
        'drf_yasg': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# ========== SWAGGER/OPENAPI SETTINGS ==========
# IMPORTANT FIXES FOR SWAGGER
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT Authorization header using the Bearer scheme. Example: "Bearer {token}"'
        },
        'APIKey': {
            'type': 'apiKey',
            'name': 'X-API-Key',
            'in': 'header',
            'description': 'API Key for service-to-service authentication'
        }
    },
    'SECURITY_REQUIREMENTS': [
        {
            'Bearer': [],
            'APIKey': []
        }
    ],
    'USE_SESSION_AUTH': False,
    'DEFAULT_API_URL': SITE_URL,
    'VALIDATOR_URL': None,  # Disable schema validator for production
    'OPERATIONS_SORTER': 'alpha',
    'TAGS_SORTER': 'alpha',
    'DEEP_LINKING': True,
    'PERSIST_AUTH': True,
    'REFETCH_SCHEMA_WITH_AUTH': True,
    'REFETCH_SCHEMA_ON_LOGOUT': True,
    # Fix for HTTPS in production
    'USE_HTTPS': SITE_URL.startswith('https://') if SITE_URL else False,
}

# DRF Spectacular settings (alternative to drf-yasg if you have issues)
# INSTALLED_APPS += ['drf_spectacular']
# REST_FRAMEWORK['DEFAULT_SCHEMA_CLASS'] = 'drf_spectacular.openapi.AutoSchema'
# SPECTACULAR_SETTINGS = {
#     'TITLE': 'Wallet Service API',
#     'DESCRIPTION': 'Wallet Service with Paystack, JWT & API Keys',
#     'VERSION': '1.0.0',
#     'SERVE_INCLUDE_SCHEMA': False,
#     'SWAGGER_UI_SETTINGS': {
#         'deepLinking': True,
#         'persistAuthorization': True,
#     },
# }

# ========== ADDITIONAL FIXES ==========
# Make sure Django can find templates
TEMPLATES[0]['DIRS'] = [os.path.join(BASE_DIR, 'templates')]  # Optional

# Ensure static files are served properly
if DEBUG:
    STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
else:
    # In production, WhiteNoise will serve static files
    pass

# Database connection pool settings (for production)
if not DEBUG and DATABASE_URL:
    DATABASES['default']['CONN_MAX_AGE'] = 60
    DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require',
    }