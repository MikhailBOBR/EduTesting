from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User, UserRole
from testing.models import (
    Announcement,
    Attempt,
    AttemptReview,
    AttemptStatus,
    Choice,
    Course,
    Enrollment,
    EnrollmentStatus,
    Question,
    QuestionType,
    Quiz,
    SemesterChoices,
)
from testing.services import submit_attempt


TEACHER_PASSWORD = 'TeacherDemo123!'
STUDENT_PASSWORD = 'StudentDemo123!'

TEACHERS = [
    ('teacher_demo', 'teacher@example.com', 'Анна', 'Соколова', 'Доцент кафедры веб-технологий.'),
    ('teacher_db', 'teacher_db@example.com', 'Сергей', 'Волков', 'Преподаватель по базам данных и SQL.'),
    ('teacher_qa', 'teacher_qa@example.com', 'Елена', 'Громова', 'Преподаватель по тестированию ПО.'),
]

STUDENTS = [
    ('student_demo', 'student@example.com', 'Илья', 'Кузнецов', 'ИС-21'),
    ('student_01', 'student01@example.com', 'Марина', 'Алексеева', 'ИС-21'),
    ('student_02', 'student02@example.com', 'Никита', 'Савельев', 'ИС-21'),
    ('student_03', 'student03@example.com', 'Ольга', 'Ларионова', 'ИС-22'),
    ('student_04', 'student04@example.com', 'Денис', 'Рябов', 'ИС-22'),
    ('student_05', 'student05@example.com', 'Виктория', 'Тихонова', 'ИС-22'),
    ('student_06', 'student06@example.com', 'Павел', 'Мельников', 'ПИ-31'),
    ('student_07', 'student07@example.com', 'Софья', 'Журавлева', 'ПИ-31'),
    ('student_08', 'student08@example.com', 'Артем', 'Никифоров', 'ПИ-31'),
    ('student_09', 'student09@example.com', 'Дарья', 'Орлова', 'ПИ-32'),
    ('student_10', 'student10@example.com', 'Егор', 'Киселев', 'ПИ-32'),
    ('student_11', 'student11@example.com', 'Полина', 'Тарасова', 'ПИ-32'),
]


def q(text, topic, qtype, difficulty, points, explanation, choices):
    return {
        'text': text,
        'topic': topic,
        'question_type': qtype,
        'difficulty': difficulty,
        'points': points,
        'explanation': explanation,
        'choices': choices,
    }


def build_course_specs():
    return [
        {
            'title': 'Основы веб-разработки',
            'owner': 'teacher_demo',
            'subject_code': 'WEB-201',
            'summary': 'HTTP, Django, шаблоны и формы.',
            'description': 'Курс по базовой архитектуре веб-приложений и разработке на Django.',
            'audience': 'Студенты 2-3 курса',
            'semester': SemesterChoices.AUTUMN,
            'academic_year': '2025/2026',
            'assessment_policy': 'Оценка складывается из тестов, лабораторных и проекта.',
            'enrollments': ['student_demo', 'student_01', 'student_02', 'student_03', 'student_04', 'student_05', 'student_06'],
            'completed': ['student_03'],
            'in_progress': ['student_demo'],
            'announcements': [
                ('Старт модуля', 'Проверьте доступ к системе и ознакомьтесь с регламентом курса.', True, -10),
                ('Открыт входной тест', 'Входной контроль доступен до конца недели.', False, -5),
            ],
            'quizzes': [
                {
                    'title': 'Входной тест по Django',
                    'description': 'Проверка MVT, ORM и структуры проекта.',
                    'instructions': 'Выберите один или несколько правильных ответов.',
                    'time_limit_minutes': 25,
                    'passing_score': 60,
                    'max_attempts': 2,
                    'show_correct_answers': True,
                    'from_days': -8,
                    'to_days': 12,
                    'questions': [
                        q('Какой паттерн лежит в основе Django?', 'MVT', QuestionType.SINGLE, 'basic', 2, 'Django использует MVT.', [('MVC', False), ('MVT', True), ('MVVM', False), ('ADR', False)]),
                        q('Что делает Django ORM?', 'ORM', QuestionType.MULTIPLE, 'intermediate', 3, 'ORM отвечает за модели, миграции и доступ к данным.', [('Миграции БД', True), ('Python API к данным', True), ('CSS-верстка', False), ('Работа с flexbox', False)]),
                        q('Где описывают URL-маршруты?', 'Маршрутизация', QuestionType.SINGLE, 'basic', 2, 'Маршруты обычно определяются в urls.py.', [('settings.py', False), ('urls.py', True), ('models.py', False), ('forms.py', False)]),
                    ],
                },
                {
                    'title': 'HTTP и шаблоны',
                    'description': 'Тест по HTTP, status codes и Django Templates.',
                    'instructions': 'На выполнение выделяется 20 минут.',
                    'time_limit_minutes': 20,
                    'passing_score': 65,
                    'max_attempts': 2,
                    'show_correct_answers': True,
                    'from_days': -2,
                    'to_days': 18,
                    'questions': [
                        q('Какие HTTP-методы считаются идемпотентными?', 'HTTP', QuestionType.MULTIPLE, 'advanced', 4, 'GET, PUT и DELETE относятся к идемпотентным.', [('GET', True), ('POST', False), ('PUT', True), ('DELETE', True)]),
                        q('Какой код означает, что ресурс не найден?', 'HTTP', QuestionType.SINGLE, 'basic', 2, 'Код 404 означает, что ресурс не найден.', [('200', False), ('302', False), ('404', True), ('500', False)]),
                        q('Для чего нужен base.html?', 'Шаблоны', QuestionType.SINGLE, 'basic', 2, 'Базовый шаблон задает общий каркас страниц.', [('Для моделей', False), ('Для общего каркаса страниц', True), ('Для миграций', False), ('Для БД', False)]),
                    ],
                },
            ],
        },
        {
            'title': 'Базы данных',
            'owner': 'teacher_db',
            'subject_code': 'DB-210',
            'summary': 'Реляционные модели, SQL, нормализация и транзакции.',
            'description': 'Курс по проектированию схем данных, SQL-запросам и транзакционной модели.',
            'audience': 'Студенты 2-3 курса',
            'semester': SemesterChoices.SPRING,
            'academic_year': '2025/2026',
            'assessment_policy': 'Оценка формируется из SQL-практикума и рубежных тестов.',
            'enrollments': ['student_demo', 'student_02', 'student_03', 'student_06', 'student_07', 'student_08', 'student_09', 'student_10'],
            'completed': ['student_09'],
            'in_progress': ['student_06'],
            'announcements': [
                ('Лабораторный практикум по SQL', 'В курс загружены задания по SELECT, JOIN и GROUP BY.', False, -7),
                ('Подготовка к рубежному контролю', 'Повторите нормализацию, индексы и транзакции.', True, -2),
            ],
            'quizzes': [
                {
                    'title': 'SQL и нормализация',
                    'description': 'Контроль знаний по SQL и нормальным формам.',
                    'instructions': 'Частичное совпадение в multiple-вопросах не засчитывается.',
                    'time_limit_minutes': 30,
                    'passing_score': 65,
                    'max_attempts': 2,
                    'show_correct_answers': True,
                    'from_days': -6,
                    'to_days': 15,
                    'questions': [
                        q('Для чего используется JOIN?', 'SQL', QuestionType.SINGLE, 'basic', 2, 'JOIN объединяет строки из нескольких таблиц.', [('Для сортировки', False), ('Для объединения таблиц', True), ('Для индексации', False), ('Для удаления столбцов', False)]),
                        q('Какие признаки характерны для 3НФ?', 'Нормализация', QuestionType.MULTIPLE, 'advanced', 4, 'Третья нормальная форма исключает транзитивные зависимости.', [('Нет транзитивных зависимостей', True), ('Все зависит только от ключа', True), ('Только один столбец в таблице', False), ('Нет внешних ключей', False)]),
                        q('Как выбрать все строки из students?', 'SQL', QuestionType.SINGLE, 'basic', 2, 'Стандартный синтаксис: SELECT * FROM students.', [('GET students', False), ('SELECT ALL students', False), ('SELECT * FROM students', True), ('SHOW students', False)]),
                    ],
                },
                {
                    'title': 'Индексы и транзакции',
                    'description': 'Проверка понимания индексов, ACID и изоляции транзакций.',
                    'instructions': 'Тест ориентирован на практику проектирования БД.',
                    'time_limit_minutes': 25,
                    'passing_score': 70,
                    'max_attempts': 2,
                    'show_correct_answers': False,
                    'from_days': 1,
                    'to_days': 22,
                    'questions': [
                        q('Для чего создают индексы?', 'Индексы', QuestionType.SINGLE, 'intermediate', 3, 'Индексы ускоряют выборку данных.', [('Для резервных копий', False), ('Для ускорения выборки', True), ('Для удаления дублей', False), ('Для смены СУБД', False)]),
                        q('Какие свойства входят в ACID?', 'Транзакции', QuestionType.MULTIPLE, 'advanced', 4, 'ACID включает атомарность, согласованность, изолированность и долговечность.', [('Атомарность', True), ('Согласованность', True), ('Изолированность', True), ('Декларативность', False)]),
                        q('Как называется чтение неподтвержденных данных?', 'Транзакции', QuestionType.SINGLE, 'advanced', 3, 'Это явление называется dirty read.', [('Dirty read', True), ('Phantom insert', False), ('Dead code', False), ('Hot standby', False)]),
                    ],
                },
            ],
        },
        {
            'title': 'Тестирование программного обеспечения',
            'owner': 'teacher_qa',
            'subject_code': 'QA-305',
            'summary': 'Тест-дизайн, регрессия, автоматизация и качество веб-систем.',
            'description': 'Курс по техникам тестирования, документации и организации процесса QA.',
            'audience': 'Студенты 3-4 курса',
            'semester': SemesterChoices.SPRING,
            'academic_year': '2025/2026',
            'assessment_policy': 'Учитываются тематические квизы, отчеты по кейсам и итоговый контроль.',
            'enrollments': ['student_01', 'student_04', 'student_05', 'student_06', 'student_07', 'student_08', 'student_09', 'student_11'],
            'completed': [],
            'in_progress': ['student_05'],
            'announcements': [
                ('Опубликован календарный план', 'В курсе доступны сроки контрольных точек и список литературы.', False, -8),
                ('Начало модуля по тест-дизайну', 'Подготовьте примеры test case и user story.', True, -3),
            ],
            'quizzes': [
                {
                    'title': 'Основы тест-дизайна',
                    'description': 'Проверка знания техник проектирования тестов.',
                    'instructions': 'Вопросы охватывают черный ящик, тест-кейсы и приоритизацию.',
                    'time_limit_minutes': 30,
                    'passing_score': 65,
                    'max_attempts': 2,
                    'show_correct_answers': True,
                    'from_days': -5,
                    'to_days': 16,
                    'questions': [
                        q('Какие техники относятся к черному ящику?', 'Тест-дизайн', QuestionType.MULTIPLE, 'intermediate', 3, 'Эквивалентное разбиение и граничные значения относятся к black-box.', [('Эквивалентное разбиение', True), ('Анализ граничных значений', True), ('Покрытие ветвей', False), ('Покрытие операторов', False)]),
                        q('Что такое тест-кейс?', 'Документация', QuestionType.SINGLE, 'basic', 2, 'Тест-кейс — формализованный сценарий проверки.', [('Список библиотек', False), ('Описание сценария проверки', True), ('Схема БД', False), ('CI-конфиг', False)]),
                        q('Что влияет на приоритизацию тестов?', 'Планирование', QuestionType.MULTIPLE, 'advanced', 4, 'Обычно учитывают риск, критичность и частоту использования.', [('Риск дефекта', True), ('Бизнес-критичность', True), ('Цвет интерфейса', False), ('Частота использования функции', True)]),
                    ],
                },
                {
                    'title': 'Регрессия и автоматизация',
                    'description': 'Тест по регрессионному тестированию и автоматизации проверок.',
                    'instructions': 'Правильные ответы показываются после завершения теста.',
                    'time_limit_minutes': 25,
                    'passing_score': 70,
                    'max_attempts': 2,
                    'show_correct_answers': True,
                    'from_days': 3,
                    'to_days': 24,
                    'questions': [
                        q('Когда особенно полезно регрессионное тестирование?', 'Регрессия', QuestionType.SINGLE, 'intermediate', 3, 'Регрессия критична после изменений в системе.', [('Только перед релизом', False), ('После изменений', True), ('Только при падении БД', False), ('Только для мобильных приложений', False)]),
                        q('Какие преимущества дает автоматизация тестов?', 'Автоматизация', QuestionType.MULTIPLE, 'intermediate', 3, 'Автотесты ускоряют повторные проверки и повышают воспроизводимость.', [('Быстрое повторное выполнение', True), ('Воспроизводимость', True), ('Интеграция в CI/CD', True), ('Отмена анализа результатов', False)]),
                        q('Что часто автоматизируют в первую очередь?', 'Практика', QuestionType.SINGLE, 'advanced', 3, 'Часто начинают со smoke- и регрессионных сценариев.', [('Smoke и регрессия', True), ('Только exploratory', False), ('Только нагрузочное тестирование', False), ('Только дизайн-ревью', False)]),
                    ],
                },
            ],
        },
        {
            'title': 'Проектный практикум по Django',
            'owner': 'teacher_demo',
            'subject_code': 'WEB-401',
            'summary': 'Практический курс по созданию законченного учебного веб-приложения.',
            'description': 'Студенты проектируют архитектуру, БД, интерфейсы, тесты и защищают готовый проект.',
            'audience': 'Студенты 4 курса',
            'semester': SemesterChoices.SPRING,
            'academic_year': '2025/2026',
            'assessment_policy': 'Основной вес имеют этапы проекта, защита архитектуры и итоговое тестирование.',
            'enrollments': ['student_demo', 'student_06', 'student_07', 'student_08', 'student_10', 'student_11'],
            'completed': [],
            'in_progress': ['student_10'],
            'announcements': [
                ('Старт проектного этапа', 'Согласуйте тему учебного веб-приложения и состав ER-модели.', True, -4),
                ('Промежуточная проверка макетов', 'В систему загружены критерии оценки интерфейса и ролей.', False, -1),
            ],
            'quizzes': [
                {
                    'title': 'Архитектура Django-проекта',
                    'description': 'Проверка знаний по MVT, приложениям и сервисному слою.',
                    'instructions': 'Подготовьтесь к вопросам по структуре проекта и разделению ответственности.',
                    'time_limit_minutes': 25,
                    'passing_score': 70,
                    'max_attempts': 2,
                    'show_correct_answers': True,
                    'from_days': -1,
                    'to_days': 20,
                    'questions': [
                        q('Зачем проект разбивают на несколько Django apps?', 'Архитектура', QuestionType.SINGLE, 'intermediate', 3, 'Разделение на apps повышает модульность и поддержку.', [('Чтобы запретить шаблоны', False), ('Чтобы структурировать предметные области', True), ('Чтобы отключить маршруты', False), ('Чтобы отказаться от БД', False)]),
                        q('Что можно вынести в сервисный слой?', 'Сервисный слой', QuestionType.MULTIPLE, 'advanced', 4, 'В сервисный слой выносят бизнес-операции и сложные сценарии.', [('Подсчет результата', True), ('Оркестрацию доменных действий', True), ('HTML-разметку', False), ('Сложные вычисления', True)]),
                        q('Почему в учебном проекте удобно использовать SQLite3?', 'База данных', QuestionType.MULTIPLE, 'basic', 3, 'SQLite проста, встроена в Django и подходит для учебной демонстрации.', [('Не требует отдельного сервера', True), ('Удобна для учебного проекта', True), ('Поддерживается Django', True), ('Всегда быстрее любой промышленной БД', False)]),
                    ],
                },
                {
                    'title': 'Тестирование и защита проекта',
                    'description': 'Тест по автоматическим проверкам и подготовке проекта к защите.',
                    'instructions': 'Вопросы охватывают тесты, требования и презентацию результата.',
                    'time_limit_minutes': 20,
                    'passing_score': 70,
                    'max_attempts': 2,
                    'show_correct_answers': True,
                    'from_days': 7,
                    'to_days': 32,
                    'questions': [
                        q('Зачем в Django-проекте пишут тесты?', 'Тестирование', QuestionType.MULTIPLE, 'basic', 3, 'Тесты помогают предотвратить регрессии и проверить бизнес-логику.', [('Проверка бизнес-логики', True), ('Контроль регрессий', True), ('Автогенерация дизайна', False), ('Подтверждение сценариев', True)]),
                        q('Что важно показать на защите учебного веб-проекта?', 'Защита', QuestionType.MULTIPLE, 'intermediate', 4, 'На защите полезно показать архитектуру, БД, сценарии и тесты.', [('Архитектуру приложения', True), ('Структуру БД', True), ('Ключевые сценарии', True), ('Только цветовую палитру', False)]),
                        q('Какой файл обычно содержит зависимости Python-проекта?', 'Структура проекта', QuestionType.SINGLE, 'basic', 2, 'Зависимости обычно фиксируют в requirements.txt.', [('requirements.txt', True), ('urls.py', False), ('base.html', False), ('db.sqlite3', False)]),
                    ],
                },
            ],
        },
    ]


class Command(BaseCommand):
    help = 'Создает расширенные демонстрационные данные для проекта онлайн-тестирования.'

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()
        course_specs = build_course_specs()

        teachers = self._seed_teachers()
        students = self._seed_students()
        courses = {}

        for spec in course_specs:
            course = self._seed_course(spec, teachers[spec['owner']], students, today, now)
            courses[spec['title']] = course

        self._seed_attempts(course_specs, courses, students, now)
        self._seed_reviews(courses, now)
        self._seed_in_progress(course_specs, courses, students, now)

        self.stdout.write(
            self.style.SUCCESS(
                'Расширенные демо-данные готовы: 3 преподавателя, 12 студентов, 4 курса, 8 тестов и заполненная аналитика.'
            )
        )
        self.stdout.write('Основные логины: teacher_demo / TeacherDemo123!, student_demo / StudentDemo123!')

    def _seed_teachers(self):
        result = {}
        for username, email, first_name, last_name, bio in TEACHERS:
            user, _ = User.objects.get_or_create(username=username, defaults={'email': email})
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.role = UserRole.TEACHER
            user.bio = bio
            user.set_password(TEACHER_PASSWORD)
            user.save()
            result[username] = user
        return result

    def _seed_students(self):
        result = {}
        for username, email, first_name, last_name, group in STUDENTS:
            user, _ = User.objects.get_or_create(username=username, defaults={'email': email})
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.role = UserRole.STUDENT
            user.academic_group = group
            user.bio = f'Студент группы {group}.'
            user.set_password(STUDENT_PASSWORD)
            user.save()
            result[username] = user
        return result

    def _seed_course(self, spec, teacher, students, today, now):
        course, _ = Course.objects.get_or_create(title=spec['title'], owner=teacher, defaults={'summary': spec['summary']})
        course.subject_code = spec['subject_code']
        course.summary = spec['summary']
        course.description = spec['description']
        course.audience = spec['audience']
        course.semester = spec['semester']
        course.academic_year = spec['academic_year']
        course.start_date = today - timedelta(days=20)
        course.end_date = today + timedelta(days=80)
        course.assessment_policy = spec['assessment_policy']
        course.is_published = True
        course.save()

        completed = set(spec.get('completed', []))
        for username in spec['enrollments']:
            Enrollment.objects.update_or_create(
                course=course,
                student=students[username],
                defaults={'status': EnrollmentStatus.COMPLETED if username in completed else EnrollmentStatus.ACTIVE},
            )

        for index, (title, body, important, offset) in enumerate(spec['announcements']):
            announcement, _ = Announcement.objects.get_or_create(course=course, title=title, defaults={'body': body})
            announcement.body = body
            announcement.is_important = important
            announcement.published_at = now + timedelta(days=offset, hours=index)
            announcement.save()

        for quiz_spec in spec['quizzes']:
            quiz, _ = Quiz.objects.get_or_create(course=course, title=quiz_spec['title'], defaults={'description': quiz_spec['description']})
            quiz.description = quiz_spec['description']
            quiz.instructions = quiz_spec['instructions']
            quiz.time_limit_minutes = quiz_spec['time_limit_minutes']
            quiz.passing_score = quiz_spec['passing_score']
            quiz.max_attempts = quiz_spec['max_attempts']
            quiz.available_from = now + timedelta(days=quiz_spec['from_days'])
            quiz.available_until = now + timedelta(days=quiz_spec['to_days'])
            quiz.show_correct_answers = quiz_spec['show_correct_answers']
            quiz.is_published = True
            quiz.save()

            for order, question_spec in enumerate(quiz_spec['questions'], start=1):
                question, _ = Question.objects.update_or_create(
                    quiz=quiz,
                    order=order,
                    defaults={
                        'text': question_spec['text'],
                        'topic': question_spec['topic'],
                        'explanation': question_spec['explanation'],
                        'question_type': question_spec['question_type'],
                        'difficulty': question_spec['difficulty'],
                        'points': question_spec['points'],
                    },
                )
                for choice_order, (text, is_correct) in enumerate(question_spec['choices'], start=1):
                    Choice.objects.update_or_create(
                        question=question,
                        order=choice_order,
                        defaults={'text': text, 'is_correct': is_correct},
                    )
        return course

    def _seed_attempts(self, specs, courses, students, now):
        profiles = ['excellent', 'good', 'average', 'weak']
        for spec in specs:
            quizzes = list(courses[spec['title']].quizzes.filter(is_published=True).order_by('title'))
            for student_index, username in enumerate(spec['enrollments']):
                student = students[username]
                for quiz_index, quiz in enumerate(quizzes):
                    if (student_index + quiz_index) % 5 == 0:
                        continue
                    max_seeded = 2 if quiz.max_attempts > 1 and (student_index + quiz_index) % 4 == 0 else 1
                    existing = Attempt.objects.filter(quiz=quiz, student=student, status=AttemptStatus.SUBMITTED).count()
                    for try_index in range(existing, min(max_seeded, quiz.max_attempts)):
                        profile = profiles[(student_index + quiz_index + try_index) % len(profiles)]
                        submitted_at = now - timedelta(days=(student_index + quiz_index + try_index) % 18, hours=quiz_index)
                        duration = max(6, min(quiz.time_limit_minutes - 1, 8 + ((student_index + quiz_index + try_index) % 9)))
                        self._create_submitted_attempt(quiz, student, profile, submitted_at, duration)

    def _seed_in_progress(self, specs, courses, students, now):
        for spec in specs:
            quizzes = list(courses[spec['title']].quizzes.filter(is_published=True).order_by('title'))
            if not quizzes:
                continue
            quiz = quizzes[0]
            for username in spec.get('in_progress', []):
                student = students[username]
                if quiz.remaining_attempts(student) <= 0:
                    continue
                attempt, _ = Attempt.objects.get_or_create(quiz=quiz, student=student, status=AttemptStatus.IN_PROGRESS)
                Attempt.objects.filter(pk=attempt.pk).update(started_at=now - timedelta(minutes=min(12, quiz.time_limit_minutes - 1)))

    def _seed_reviews(self, courses, now):
        feedback_map = {
            'excellent': 'Результат уверенный. Можно переходить к следующему разделу курса.',
            'good': 'Хорошая работа. Стоит дополнительно повторить 1-2 темы с ошибками.',
            'average': 'Есть рабочая база, но по нескольким вопросам нужен повтор теории.',
            'weak': 'Нужно еще раз разобрать материал и вернуться к тесту после повторения.',
        }
        reviewed_attempts = (
            Attempt.objects.filter(
                quiz__course__in=courses.values(),
                status=AttemptStatus.SUBMITTED,
            )
            .select_related('quiz__course__owner')
            .order_by('quiz__course_id', '-score_percent', 'submitted_at')[:18]
        )

        for attempt in reviewed_attempts:
            if attempt.score_percent >= 85:
                profile = 'excellent'
            elif attempt.score_percent >= 65:
                profile = 'good'
            elif attempt.score_percent >= 45:
                profile = 'average'
            else:
                profile = 'weak'

            AttemptReview.objects.update_or_create(
                attempt=attempt,
                defaults={
                    'teacher': attempt.quiz.course.owner,
                    'feedback': feedback_map[profile],
                    'reviewed_at': (attempt.submitted_at or now) + timedelta(hours=6),
                },
            )

    def _create_submitted_attempt(self, quiz, student, profile, submitted_at, duration_minutes):
        attempt = Attempt.objects.create(quiz=quiz, student=student)
        submit_attempt(attempt, self._build_answers_mapping(quiz, profile))
        Attempt.objects.filter(pk=attempt.pk).update(
            started_at=submitted_at - timedelta(minutes=duration_minutes),
            submitted_at=submitted_at,
            duration_seconds=duration_minutes * 60,
        )

    def _build_answers_mapping(self, quiz, profile):
        mapping = {}
        for index, question in enumerate(quiz.questions.prefetch_related('choices').order_by('order'), start=1):
            correct = list(question.choices.filter(is_correct=True).values_list('id', flat=True))
            incorrect = list(question.choices.filter(is_correct=False).values_list('id', flat=True))
            if profile == 'excellent':
                selected = set(correct)
            elif profile == 'good':
                selected = set(correct if index % 4 != 0 else incorrect[:1])
            elif profile == 'average':
                selected = set(correct if index % 2 == 0 else incorrect[:1])
            else:
                selected = set(correct if index == 1 else incorrect[:1])
            mapping[question.id] = selected
        return mapping
