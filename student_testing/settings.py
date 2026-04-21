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
        'Полноценный API платформы онлайн-тестирования студентов с акцентом на практические backend-сценарии: '
        'автосохранение черновика, сравнение попыток, достижения, аналитика курса, индивидуальные условия, '
        'апелляции и контроль подозрительных попыток.\n\n'
        'Что особенно удобно демонстрировать в Swagger UI:\n'
        '* токен-авторизацию и разделение ролей пользователя;\n'
        '* студенческий поток: запись на курс, старт попытки, автосохранение, отправка, результат и достижения;\n'
        '* преподавательский поток: аналитика курса, integrity-контроль, индивидуальные условия и рассмотрение апелляций;\n'
        '* публичные обзорные методы: статистику сервиса, каталог курсов, описание курса и теста.\n\n'
        'Для защищенных методов сначала выполните `POST /api/auth/token/`, затем нажмите `Authorize` '
        'и передайте токен в формате `Token ваш_токен`.'
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
            'description': 'Получение токена для работы в Swagger UI и Postman.',
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
            'description': 'Тесты курса, старт попытки, индивидуальные условия и журнал попыток.',
        },
        {
            'name': 'attempts',
            'description': 'Черновики, итог попытки, сравнение с прошлой попыткой и апелляции.',
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
