# Демонстрация API

Сопутствующие материалы:

- [README.md](../README.md)
- [Wiki: API и интеграции](wiki/api.md)
- [Wiki: релизная проверка](wiki/release-checklist.md)

## Что покрывает API

API в EduTesting дополняет основной web-интерфейс и позволяет показать ключевые
серверные сценарии:

- token auth и смену пароля
- поток студента: запись на курс, старт попытки, автосохранение, отправку и просмотр результата
- достижения студента
- поток преподавателя: аналитику курса, индивидуальные условия, журнал попыток и апелляции
- контроль подозрительных попыток

## Основные адреса

- Swagger UI: `GET /api/docs/`
- OpenAPI schema: `GET /api/schema/`
- токен: `POST /api/auth/token/`
- смена пароля: `POST /api/auth/password/change/`
- текущий пользователь: `GET /api/me/`
- админ-панель: `GET /admin/`

Локальный адрес после запуска проекта:

```text
http://127.0.0.1:8000/api/docs/
```

## Готовые материалы для Postman

В проекте уже подготовлены файлы:

- [docs/EduTesting.postman_collection.json](EduTesting.postman_collection.json)
- [docs/EduTesting.postman_environment.json](EduTesting.postman_environment.json)

Что есть в коллекции:

- папка `Public Overview`
- папка `Auth`
- папка `Student Flow`
- папка `Teacher Flow`
- папка `Admin Web`
- автоматическое сохранение `student_token`
- автоматическое сохранение `teacher_token`
- автоматическое сохранение `attempt_id`
- автоматическое сохранение `appeal_id`
- отдельные запросы для безопасной смены и восстановления пароля
- встроенные Postman-tests, чтобы на скриншотах были видны успешные проверки ответов

## Что показать в Swagger

Минимальный сильный сценарий:

1. `POST /api/auth/token/`
2. `POST /api/auth/password/change/`
3. `GET /api/stats/`
4. `GET /api/courses/`
5. `POST /api/quizzes/{id}/start/`
6. `POST /api/attempts/{id}/draft/`
7. `POST /api/attempts/{id}/submit/`
8. `GET /api/my/achievements/`
9. `GET /api/courses/{id}/analytics/`
10. `GET /api/courses/{id}/integrity/`

Особенно хорошо смотрятся:

- `POST /api/auth/password/change/` — безопасность и полноценная работа с аккаунтом через API
- `GET /api/my/achievements/` — вычисляемые достижения без отдельной сущности в БД
- `GET /api/courses/{id}/integrity/` — преподавательский контроль подозрительных попыток
- `GET /api/attempts/{id}/` — результат попытки, сравнение с прошлой попыткой и новые достижения
- `GET /api/courses/{id}/analytics/` — тема курса, проблемные студенты и лидерборд

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
5. `GET /api/quizzes/{id}/overrides/`
6. `POST /api/quizzes/{id}/overrides/`
7. `POST /api/appeals/{id}/review/`

### Сценарий безопасности и администрирования

1. `POST /api/auth/password/change/`
2. `GET /admin/login/`

## Рекомендуемый набор скриншотов

Для сильной демонстрации работоспособности API удобно подготовить такие экраны:

1. Swagger UI с авторизацией и раскрытым `POST /api/auth/token/`
2. Swagger UI с `POST /api/auth/password/change/`
3. Swagger UI с `POST /api/attempts/{id}/submit/`
4. Swagger UI с `GET /api/my/achievements/`
5. Swagger UI с `GET /api/courses/{id}/analytics/`
6. Swagger UI с `GET /api/courses/{id}/integrity/`
7. Postman: успешное получение токена
8. Postman: студентческий сценарий `start -> draft -> submit`
9. Postman: смена пароля через API
10. Postman: преподавательский сценарий `analytics -> integrity -> review appeal`
11. Postman: открытие страницы `/admin/login/`

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

## Пример смены пароля

```http
POST /api/auth/password/change/
Content-Type: application/json
Authorization: Token ваш_токен
```

```json
{
  "current_password": "StudentDemo123!",
  "new_password": "StudentDemo456!",
  "new_password_confirm": "StudentDemo456!"
}
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
- администратор: `admin_demo` / `AdminDemo123!`

## Примечание по demo-id

В environment по умолчанию заданы:

- `course_id = 1`
- `quiz_id = 1`
- `override_student_id = 6`

Если после повторного наполнения базы идентификаторы изменятся, достаточно обновить их
один раз в Postman environment.
