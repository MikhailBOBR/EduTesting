# Демонстрация API в отчете

## Назначение

В проекте реализован **полноценный, но не перегруженный REST API** для демонстрации серверной части через `Swagger` и `Postman`.

API не заменяет основной web-интерфейс на `Django Templates`, а дополняет его и позволяет показать в отчете:

- публичные данные сервиса;
- авторизацию пользователя;
- сценарий студента;
- сценарий преподавателя;
- корректную OpenAPI-документацию.

## Базовые адреса

- `GET /api/docs/` — Swagger UI
- `GET /api/schema/` — OpenAPI schema
- `POST /api/auth/token/` — получение токена
- `GET /api/me/` — текущий пользователь

Swagger после запуска проекта:

```text
http://127.0.0.1:8000/api/docs/
```

## Основные эндпоинты

### Публичные

- `GET /api/stats/`
- `GET /api/courses/`
- `GET /api/courses/<id>/`
- `GET /api/quizzes/<id>/`

### Авторизованные

- `POST /api/auth/token/`
- `GET /api/me/`
- `GET /api/my/courses/`

### Сценарий студента

- `POST /api/courses/<id>/enroll/`
- `POST /api/quizzes/<id>/start/`
- `POST /api/attempts/<id>/submit/`
- `GET /api/attempts/<id>/`

### Сценарий преподавателя

- `GET /api/courses/<id>/analytics/`
- `GET /api/quizzes/<id>/attempts/`

## Что показывать в Postman

Для отчета достаточно 6-7 скриншотов.

### Вариант последовательности

1. `POST /api/auth/token/` под студентом  
   Показывает успешную авторизацию и получение токена.

2. `GET /api/me/`  
   Показывает, что токен работает и API определяет пользователя.

3. `POST /api/courses/<id>/enroll/`  
   Демонстрирует запись студента на курс.

4. `POST /api/quizzes/<id>/start/`  
   Демонстрирует создание попытки.

5. `POST /api/attempts/<id>/submit/`  
   Демонстрирует отправку ответов и получение результата.

6. `GET /api/attempts/<id>/`  
   Показывает подробный отчет по попытке, ответы и аналитику по темам.

7. `GET /api/courses/<id>/analytics/` под преподавателем  
   Показывает аналитику курса, рейтинг и список студентов, которым нужно внимание.

## Пример авторизации в Postman

### Шаг 1. Получить токен

Запрос:

```http
POST /api/auth/token/
Content-Type: application/json
```

Тело:

```json
{
  "username": "student_demo",
  "password": "StudentDemo123!"
}
```

Ответ:

```json
{
  "token": "ваш_токен",
  "user": {
    "id": 4,
    "username": "student_demo",
    "full_name": "Илья Кузнецов",
    "role": "student",
    "email": "student@example.com",
    "academic_group": "ИС-21"
  }
}
```

### Шаг 2. Передавать токен в заголовке

```http
Authorization: Token ваш_токен
```

## Пример отправки попытки

```http
POST /api/attempts/1/submit/
Content-Type: application/json
Authorization: Token ваш_токен
```

```json
{
  "answers": {
    "1": [2],
    "2": [4, 6]
  }
}
```

## Что показывать в Swagger

Для `Swagger` удобно сделать 4 скриншота:

1. Главная страница `Swagger UI` со всеми доступными методами.
2. Блок авторизации `POST /api/auth/token/`.
3. Студенческий сценарий: `POST /api/quizzes/<id>/start/` или `POST /api/attempts/<id>/submit/`.
4. Преподавательский сценарий: `GET /api/courses/<id>/analytics/`.

## Комментарий для пояснительной записки

В отчет можно вставить такой абзац:

> Для дополнительной демонстрации работоспособности серверной части в проекте реализован REST API с OpenAPI-документацией. Тестирование API выполнялось через Swagger UI и Postman. API поддерживает как публичные запросы на получение данных, так и авторизованные сценарии студента и преподавателя: получение токена, запись на курс, запуск и отправку попытки, просмотр результатов и аналитики курса.

## Как запустить

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

## Тестовые аккаунты для API

### Студент

- `student_demo` / `StudentDemo123!`

### Преподаватель

- `teacher_demo` / `TeacherDemo123!`
