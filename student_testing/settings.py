import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-jb7nq!-8(iaix3!eb+1*6=3l0tq7vk0)^pyfdxs#954#-jv_0f',
)
DEBUG = os.getenv('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,testserver').split(',')
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'accounts',
    'testing',
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

ROOT_URLCONF = 'student_testing.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'student_testing.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.ScryptPasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'

USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = Path(os.getenv('DJANGO_STATIC_ROOT', BASE_DIR / 'staticfiles'))

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'testing:dashboard'
LOGOUT_REDIRECT_URL = 'testing:home'
AUTH_USER_MODEL = 'accounts.User'

LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCKOUT_SECONDS = 300

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
TEST_RUNNER = 'testing.test_runner.PrettyDiscoverRunner'

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'EduTesting API',
    'DESCRIPTION': (
        'Полноценный API платформы онлайн-тестирования студентов с акцентом на '
        'практические backend-сценарии: безопасную авторизацию, автосохранение '
        'черновика, сравнение попыток, достижения, аналитику курса, индивидуальные '
        'условия, апелляции, контроль подозрительных попыток и административное '
        'сопровождение проекта.\n\n'
        'Что особенно удобно демонстрировать в Swagger UI:\n'
        '* токен-авторизацию, смену пароля и защиту от перебора паролей;\n'
        '* студенческий поток: запись на курс, старт попытки, автосохранение, отправку и просмотр результата;\n'
        '* преподавательский поток: аналитику курса, integrity-контроль, индивидуальные условия и рассмотрение апелляций;\n'
        '* обзорные публичные методы: статистику сервиса, каталог курсов и описание тестов.\n\n'
        'Для защищенных методов сначала выполните `POST /api/auth/token/`, затем нажмите '
        '`Authorize` и передайте токен в формате `Token ваш_токен`.'
    ),
    'VERSION': '1.0.0',
    'CONTACT': {
        'name': 'Кашпирев М.Д.',
    },
    'LICENSE': {
        'name': 'All rights reserved',
    },
    'SERVERS': [
        {
            'url': 'http://127.0.0.1:8000',
            'description': 'Локальный сервер разработки',
        },
    ],
    'TAGS': [
        {
            'name': 'auth',
            'description': 'Получение токена, защищенная смена пароля и контроль неудачных попыток входа.',
        },
        {
            'name': 'me',
            'description': 'Информация о текущем авторизованном пользователе.',
        },
        {
            'name': 'my',
            'description': 'Личные подборки пользователя: курсы и вычисляемые достижения.',
        },
        {
            'name': 'stats',
            'description': 'Краткая публичная статистика сервиса.',
        },
        {
            'name': 'courses',
            'description': 'Каталог курсов, запись студента, аналитика и контроль попыток по курсу.',
        },
        {
            'name': 'quizzes',
            'description': 'Тесты курса, старт попытки, индивидуальные условия и журнал завершенных работ.',
        },
        {
            'name': 'attempts',
            'description': 'Черновики, результат попытки, сравнение с прошлой попыткой и апелляции.',
        },
        {
            'name': 'appeals',
            'description': 'Рассмотрение апелляций преподавателем.',
        },
    ],
    'ENUM_NAME_OVERRIDES': {
        'AttemptStatusEnum': [
            ('in_progress', 'В процессе'),
            ('submitted', 'Завершена'),
        ],
        'EnrollmentStatusEnum': [
            ('active', 'Активное обучение'),
            ('completed', 'Курс завершен'),
            ('archived', 'Архивная запись'),
        ],
        'AppealStatusEnum': [
            ('pending', 'Ожидает решения'),
            ('approved', 'Принята'),
            ('rejected', 'Отклонена'),
        ],
    },
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'displayRequestDuration': True,
        'docExpansion': 'list',
        'filter': True,
        'persistAuthorization': True,
        'tagsSorter': 'alpha',
        'operationsSorter': 'alpha',
        'showExtensions': True,
        'showCommonExtensions': True,
        'defaultModelsExpandDepth': 1,
        'defaultModelExpandDepth': 2,
        'tryItOutEnabled': True,
        'syntaxHighlight': {
            'theme': 'obsidian',
        },
    },
}
