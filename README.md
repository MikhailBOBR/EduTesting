# EduTesting

EduTesting — веб-приложение для онлайн-тестирования студентов на `Django`.
Проект сочетает простой интерфейс на `Django Templates` и сильную серверную часть: автоматическую проверку попыток, аналитику по темам, персональные условия, апелляции, уведомления, достижения и контроль подозрительных попыток.

## Что умеет система

### Для студента

- подключение к курсу;
- прохождение тестов с ограничением по времени и попыткам;
- автосохранение черновика попытки;
- просмотр подробного результата с разбором ответов;
- сравнение с предыдущей попыткой;
- подача апелляции;
- просмотр уведомлений;
- личные достижения по попыткам и курсам.

### Для преподавателя

- создание и публикация курсов, тестов, вопросов и вариантов ответов;
- публикация объявлений;
- просмотр всех завершенных попыток по тесту;
- комментарии к попыткам;
- выдача индивидуальных условий по тесту;
- аналитика по темам и рейтинг по курсу;
- список студентов, которым нужно внимание;
- контроль подозрительных попыток по курсу;
- экспорт результатов курса в `CSV`.

### Сильные backend-фичи

- диагностика по темам после завершения попытки;
- сравнение результата с предыдущей попыткой;
- вычисляемые достижения без усложнения фронтенда;
- флаги контроля честности:
  - идеальный результат за короткое время;
  - слишком быстрое завершение;
  - резкий скачок между попытками;
- преподавательская сводка по подозрительным попыткам;
- API со Swagger и готовой коллекцией Postman.

## Технологии

- `Python`
- `Django`
- `Django ORM`
- `SQLite3`
- `Django REST Framework`
- `drf-spectacular`
- `Swagger UI`
- `Django Templates`
- `HTML + CSS`

## Архитектура

Проект построен по паттерну `MVT`.

- `models` — предметные сущности и расчётные свойства;
- `views` — web-flow преподавателя и студента;
- `templates` — простой интерфейс без SPA;
- `services.py` — сервисные сценарии вроде проверки попытки, автосохранения и уведомлений;
- `analytics.py` — рейтинг, диагностика по темам, сравнение попыток, достижения и контроль честности;
- `api_views.py` / `api_serializers.py` — REST API и OpenAPI-описание.

## Быстрый запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

После запуска:

- web-интерфейс: `http://127.0.0.1:8000/`
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`

## Демо-данные

Команда:

```bash
python manage.py seed_demo_data
```

Создает насыщенный набор данных для демонстрации:

- преподавателей и студентов;
- курсы, тесты, вопросы и варианты ответов;
- завершенные попытки;
- комментарии преподавателя;
- уведомления;
- индивидуальные условия по тестам;
- примеры апелляций;
- материал для аналитики, достижений и контроля подозрительных попыток.

### Основные аккаунты

- преподаватель: `teacher_demo` / `TeacherDemo123!`
- студент: `student_demo` / `StudentDemo123!`

### Дополнительные аккаунты

- преподаватель: `teacher_test` / `TeacherTest123!`
- студент: `student_test` / `StudentTest123!`

## Ключевые web-маршруты

- `/` — главная страница
- `/courses/` — каталог курсов
- `/dashboard/` — рабочая панель
- `/courses/<id>/` — страница курса
- `/courses/<id>/insights/` — диагностика курса
- `/quizzes/<id>/` — страница теста
- `/quizzes/<id>/attempts/` — попытки студентов по тесту
- `/attempts/<id>/result/` — результат попытки
- `/notifications/` — центр уведомлений

## Ключевые API-маршруты

### Базовые

- `POST /api/auth/token/`
- `GET /api/me/`
- `GET /api/stats/`
- `GET /api/courses/`
- `GET /api/courses/<id>/`
- `GET /api/quizzes/<id>/`

### Студент

- `GET /api/my/courses/`
- `GET /api/my/achievements/`
- `POST /api/courses/<id>/enroll/`
- `POST /api/quizzes/<id>/start/`
- `POST /api/attempts/<id>/draft/`
- `POST /api/attempts/<id>/submit/`
- `GET /api/attempts/<id>/`
- `POST /api/attempts/<id>/appeal/`

### Преподаватель

- `GET /api/courses/<id>/analytics/`
- `GET /api/courses/<id>/integrity/`
- `GET /api/quizzes/<id>/attempts/`
- `GET /api/quizzes/<id>/overrides/`
- `POST /api/quizzes/<id>/overrides/`
- `POST /api/appeals/<id>/review/`

## Swagger и Postman

В проекте уже подготовлены материалы для проверки API:

- [schema.yaml](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/schema.yaml>) — OpenAPI schema;
- [docs/api_demo.md](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/docs/api_demo.md>) — краткий сценарий демонстрации API;
- [docs/EduTesting.postman_collection.json](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/docs/EduTesting.postman_collection.json>) — готовая коллекция Postman;
- [docs/EduTesting.postman_environment.json](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/docs/EduTesting.postman_environment.json>) — локальное environment для Postman.

## Тестирование

Запуск всех автотестов:

```bash
python manage.py test
```

Запуск тестов приложения `testing`:

```bash
python manage.py test testing
```

Проверяются:

- модели и формы;
- сервисы проверки попыток и автосохранения;
- аналитика по темам;
- достижения и контроль подозрительных попыток;
- web-flow студента и преподавателя;
- права доступа;
- API, Swagger и OpenAPI schema.

## Структура проекта

```text
KyrsBACK/
|-- accounts/
|-- docs/
|-- static/
|-- student_testing/
|-- templates/
|-- testing/
|-- manage.py
|-- requirements.txt
`-- schema.yaml
```

## Документы проекта

- [docs/project_report.md](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/docs/project_report.md>)
- [docs/api_demo.md](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/docs/api_demo.md>)
