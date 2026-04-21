from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-jb7nq!-8(iaix3!eb+1*6=3l0tq7vk0)^pyfdxs#954#-jv_0f'
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']

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

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'

USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'testing:dashboard'
LOGOUT_REDIRECT_URL = 'testing:home'
AUTH_USER_MODEL = 'accounts.User'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

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
        'Аккуратный демонстрационный API для курсового проекта по онлайн-тестированию студентов.\n\n'
        'Что удобно показывать прямо в Swagger UI:\n'
        '* авторизацию по токену;\n'
        '* сценарий студента: запись на курс, старт попытки, автосохранение черновика и отправка;\n'
        '* сценарий преподавателя: просмотр попыток и аналитики курса.\n\n'
        'Для защищенных методов сначала выполните `POST /api/auth/token/`, затем нажмите `Authorize` '
        'и передайте токен в формате `Token ваш_токен`.'
    ),
    'VERSION': '1.0.0',
    'CONTACT': {
        'name': 'Кашпирев М.Д.',
    },
    'TAGS': [
        {
            'name': 'auth',
            'description': 'Получение токена для работы в Swagger UI и Postman.',
        },
        {
            'name': 'me',
            'description': 'Информация о текущем авторизованном пользователе.',
        },
        {
            'name': 'stats',
            'description': 'Краткая публичная статистика сервиса.',
        },
        {
            'name': 'courses',
            'description': 'Каталог курсов, запись студента и преподавательская аналитика.',
        },
        {
            'name': 'quizzes',
            'description': 'Тесты курса, старт попытки и список завершенных попыток.',
        },
        {
            'name': 'attempts',
            'description': 'Черновики, результат попытки и финальная отправка на проверку.',
        },
    ],
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'displayRequestDuration': True,
        'docExpansion': 'list',
        'filter': True,
        'persistAuthorization': True,
        'tagsSorter': 'alpha',
        'operationsSorter': 'alpha',
        'defaultModelsExpandDepth': 1,
        'defaultModelExpandDepth': 2,
        'tryItOutEnabled': True,
        'syntaxHighlight': {
            'theme': 'obsidian',
        },
    },
}
