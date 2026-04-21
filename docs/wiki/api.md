# API и интеграции

## Формат API

Проект предоставляет REST API на базе `Django REST Framework`.

API нужен для двух задач:

- программный доступ к ключевым сценариям системы;
- удобная демонстрация работы сервиса через Swagger UI и Postman.

## Основные группы эндпоинтов

### Базовые

- `POST /api/auth/token/`
- `GET /api/me/`
- `GET /api/stats/`

### Курсы

- `GET /api/courses/`
- `GET /api/courses/{id}/`
- `POST /api/courses/{id}/enroll/`
- `GET /api/courses/{id}/analytics/`
- `GET /api/courses/{id}/integrity/`

### Тесты и попытки

- `GET /api/quizzes/{id}/`
- `POST /api/quizzes/{id}/start/`
- `GET /api/quizzes/{id}/attempts/`
- `GET /api/quizzes/{id}/overrides/`
- `POST /api/quizzes/{id}/overrides/`
- `GET /api/attempts/{id}/`
- `POST /api/attempts/{id}/draft/`
- `POST /api/attempts/{id}/submit/`
- `POST /api/attempts/{id}/appeal/`
- `POST /api/appeals/{id}/review/`

### Личные подборки

- `GET /api/my/courses/`
- `GET /api/my/achievements/`

## Swagger UI

Swagger доступен по адресу `GET /api/docs/`.

В проекте он не оставлен в стандартном виде:

- есть аккуратный фирменный экран;
- описаны теги и сценарии;
- включены примеры тел запросов;
- сохранение авторизации работает прямо в UI.

## Postman

В `docs/` лежат готовые файлы:

- `EduTesting.postman_collection.json`
- `EduTesting.postman_environment.json`

Коллекция уже содержит:

- сценарий авторизации;
- поток студента;
- поток преподавателя;
- запросы для достижений и контроля подозрительных попыток.

## Где смотреть реализацию

- [testing/api_views.py](../../testing/api_views.py)
- [testing/api_serializers.py](../../testing/api_serializers.py)
- [testing/api_urls.py](../../testing/api_urls.py)
- [schema.yaml](../../schema.yaml)
- [docs/api_demo.md](../api_demo.md)

## Что стоит показать на демонстрации

- получение токена;
- старт попытки;
- автосохранение черновика;
- отправку попытки;
- просмотр результата;
- достижения студента;
- аналитику курса;
- контроль подозрительных попыток;
- работу с апелляциями.
