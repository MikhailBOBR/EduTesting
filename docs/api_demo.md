# Демонстрация API

## Что покрывает API

API в EduTesting дополняет основной web-интерфейс и позволяет показать ключевые серверные сценарии:

- авторизацию по токену;
- поток студента: запись на курс, старт попытки, автосохранение, отправка и просмотр результата;
- вычисляемые достижения студента;
- поток преподавателя: аналитика курса, индивидуальные условия, журнал попыток и апелляции;
- контроль подозрительных попыток по курсу.

## Основные адреса

- Swagger UI: `GET /api/docs/`
- OpenAPI schema: `GET /api/schema/`
- токен: `POST /api/auth/token/`
- текущий пользователь: `GET /api/me/`

Локальный адрес после запуска проекта:

```text
http://127.0.0.1:8000/api/docs/
```

## Готовые материалы для Postman

В проекте уже подготовлены файлы:

- [docs/EduTesting.postman_collection.json](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/docs/EduTesting.postman_collection.json>)
- [docs/EduTesting.postman_environment.json](</c:/Users/Михаил/Desktop/6semac/KyrsBACK/docs/EduTesting.postman_environment.json>)

Что есть внутри коллекции:

- папка `Auth`
- папка `Student Flow`
- папка `Teacher Flow`
- автоматическое сохранение `student_token`
- автоматическое сохранение `teacher_token`
- автоматическое сохранение `attempt_id`
- готовые тела запросов для `draft`, `submit`, `appeal`, `override`

## Что показать в Swagger

Минимальный сильный сценарий:

1. `POST /api/auth/token/`
2. `POST /api/quizzes/{id}/start/`
3. `POST /api/attempts/{id}/draft/`
4. `POST /api/attempts/{id}/submit/`
5. `GET /api/my/achievements/`
6. `GET /api/courses/{id}/analytics/`
7. `GET /api/courses/{id}/integrity/`

Особенно хорошо смотрятся:

- `GET /api/my/achievements/` — вычисляемые достижения без отдельной сущности в БД;
- `GET /api/courses/{id}/integrity/` — преподавательский контроль подозрительных попыток;
- `GET /api/attempts/{id}/` — результат попытки, сравнение с прошлой попыткой и новые достижения;
- `GET /api/courses/{id}/analytics/` — тема курса, проблемные студенты и лидерборд.

## Что показать в Postman

### Сценарий студента

1. `POST /api/auth/token/`
2. `GET /api/me/`
3. `POST /api/courses/{id}/enroll/`
4. `POST /api/quizzes/{id}/start/`
5. `POST /api/attempts/{id}/draft/`
6. `POST /api/attempts/{id}/submit/`
7. `GET /api/attempts/{id}/`
8. `GET /api/my/achievements/`
9. `POST /api/attempts/{id}/appeal/`

### Сценарий преподавателя

1. `POST /api/auth/token/`
2. `GET /api/courses/{id}/analytics/`
3. `GET /api/courses/{id}/integrity/`
4. `GET /api/quizzes/{id}/attempts/`
5. `POST /api/quizzes/{id}/overrides/`
6. `POST /api/appeals/{id}/review/`

## Пример авторизации

Запрос:

```http
POST /api/auth/token/
Content-Type: application/json
```

```json
{
  "username": "student_demo",
  "password": "StudentDemo123!"
}
```

После ответа токен передается так:

```http
Authorization: Token ваш_токен
```

## Пример автосохранения черновика

```http
POST /api/attempts/1/draft/
Content-Type: application/json
Authorization: Token ваш_токен
```

```json
{
  "answers": {
    "1": [2]
  },
  "last_question_id": 1
}
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

## Тестовые аккаунты для API

- студент: `student_demo` / `StudentDemo123!`
- преподаватель: `teacher_demo` / `TeacherDemo123!`

## Примечание по demo-id

В environment по умолчанию заданы:

- `course_id = 1`
- `quiz_id = 1`
- `override_student_id = 6`

Если после повторного наполнения базы идентификаторы изменятся, достаточно обновить их один раз в Postman environment.
