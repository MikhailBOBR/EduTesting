import random
import string
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Avg, Q, Sum
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SemesterChoices(models.TextChoices):
    AUTUMN = 'autumn', 'Осенний семестр'
    SPRING = 'spring', 'Весенний семестр'


class EnrollmentStatus(models.TextChoices):
    ACTIVE = 'active', 'Активное обучение'
    COMPLETED = 'completed', 'Курс завершен'
    ARCHIVED = 'archived', 'Архивная запись'


class DifficultyLevel(models.TextChoices):
    BASIC = 'basic', 'Базовый'
    INTERMEDIATE = 'intermediate', 'Повышенный'
    ADVANCED = 'advanced', 'Высокий'


class Course(TimeStampedModel):
    title = models.CharField('Название', max_length=200)
    subject_code = models.CharField('Код дисциплины', max_length=30, blank=True)
    summary = models.CharField('Краткое описание', max_length=255)
    description = models.TextField('Подробное описание')
    audience = models.CharField('Целевая аудитория', max_length=120, blank=True)
    semester = models.CharField(
        'Семестр',
        max_length=10,
        choices=SemesterChoices.choices,
        default=SemesterChoices.AUTUMN,
    )
    academic_year = models.CharField('Учебный год', max_length=20, default='2025/2026')
    start_date = models.DateField('Дата начала', null=True, blank=True)
    end_date = models.DateField('Дата завершения', null=True, blank=True)
    assessment_policy = models.TextField('Политика оценивания', blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_courses',
        verbose_name='Преподаватель',
    )
    access_code = models.CharField('Код курса', max_length=12, unique=True, blank=True)
    is_published = models.BooleanField('Опубликован', default=True)

    class Meta:
        ordering = ('title',)
        verbose_name = 'Курс'
        verbose_name_plural = 'Курсы'

    def __str__(self):
        return self.title

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError('Дата завершения курса не может быть раньше даты начала.')

    def save(self, *args, **kwargs):
        if not self.access_code:
            self.access_code = self.generate_access_code()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_access_code(length=8):
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(random.choices(alphabet, k=length))
            if not Course.objects.filter(access_code=code).exists():
                return code

    @property
    def total_students(self):
        return self.enrollments.filter(status=EnrollmentStatus.ACTIVE).count()

    @property
    def published_quizzes_count(self):
        return self.quizzes.filter(is_published=True).count()

    @property
    def average_score(self):
        average = self.quizzes.filter(attempts__status=AttemptStatus.SUBMITTED).aggregate(
            avg=Avg('attempts__score_percent')
        )['avg']
        return round(average or 0)

    @property
    def completion_rate(self):
        total_students = self.total_students
        if total_students == 0:
            return 0

        students_with_attempts = (
            self.quizzes.filter(attempts__status=AttemptStatus.SUBMITTED)
            .values('attempts__student')
            .distinct()
            .count()
        )
        return round((students_with_attempts / total_students) * 100)


class Enrollment(TimeStampedModel):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='Курс',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='Студент',
    )
    status = models.CharField(
        'Статус записи',
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE,
    )

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Запись на курс'
        verbose_name_plural = 'Записи на курсы'
        constraints = [
            models.UniqueConstraint(fields=('course', 'student'), name='unique_course_enrollment'),
        ]

    def __str__(self):
        return f'{self.student} -> {self.course}'


class Quiz(TimeStampedModel):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='quizzes',
        verbose_name='Курс',
    )
    title = models.CharField('Название теста', max_length=200)
    description = models.TextField('Описание', blank=True)
    instructions = models.TextField('Инструкция', blank=True)
    time_limit_minutes = models.PositiveIntegerField('Лимит времени, мин.', default=20)
    passing_score = models.PositiveIntegerField('Проходной балл, %', default=60)
    max_attempts = models.PositiveIntegerField('Максимум попыток', default=1)
    is_published = models.BooleanField('Опубликован', default=True)
    available_from = models.DateTimeField('Доступен с', null=True, blank=True)
    available_until = models.DateTimeField('Доступен до', null=True, blank=True)
    show_correct_answers = models.BooleanField('Показывать правильные ответы студенту', default=True)

    class Meta:
        ordering = ('title',)
        verbose_name = 'Тест'
        verbose_name_plural = 'Тесты'

    def __str__(self):
        return f'{self.course.title}: {self.title}'

    @property
    def total_points(self):
        return self.questions.aggregate(total=Sum('points'))['total'] or 0

    @property
    def question_count(self):
        return self.questions.count()

    @property
    def submitted_attempts_count(self):
        return self.attempts.filter(status=AttemptStatus.SUBMITTED).count()

    @property
    def average_score(self):
        average = self.attempts.filter(status=AttemptStatus.SUBMITTED).aggregate(avg=Avg('score_percent'))['avg']
        return round(average or 0)

    @property
    def pass_rate(self):
        submitted = self.attempts.filter(status=AttemptStatus.SUBMITTED)
        total = submitted.count()
        if total == 0:
            return 0
        passed = submitted.filter(score_percent__gte=self.passing_score).count()
        return round((passed / total) * 100)

    @property
    def is_available(self):
        now = timezone.now()
        if not self.is_published:
            return False
        if self.available_from and self.available_from > now:
            return False
        if self.available_until and self.available_until < now:
            return False
        return True

    @property
    def unanswered_configuration_count(self):
        count = 0
        for question in self.questions.prefetch_related('choices').all():
            if not question.choices.filter(is_correct=True).exists():
                count += 1
        return count

    def get_access_override(self, user):
        user_id = getattr(user, 'id', None)
        if not user_id:
            return None
        return self.access_overrides.filter(student_id=user_id, is_active=True).first()

    def get_effective_time_limit(self, user):
        override = self.get_access_override(user)
        return self.time_limit_minutes + (override.extra_time_minutes if override else 0)

    def get_effective_max_attempts(self, user):
        override = self.get_access_override(user)
        return self.max_attempts + (override.extra_attempts if override else 0)

    def remaining_attempts(self, user):
        user_id = getattr(user, 'id', None)
        if not user_id:
            return self.max_attempts
        completed_attempts = self.attempts.filter(
            student=user,
            status=AttemptStatus.SUBMITTED,
        ).count()
        return max(self.get_effective_max_attempts(user) - completed_attempts, 0)


class QuizAccessOverride(TimeStampedModel):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='access_overrides',
        verbose_name='Тест',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_access_overrides',
        verbose_name='Студент',
    )
    extra_time_minutes = models.PositiveIntegerField('Дополнительное время, мин.', default=0)
    extra_attempts = models.PositiveIntegerField('Дополнительные попытки', default=0)
    notes = models.TextField('Комментарий преподавателя', blank=True)
    is_active = models.BooleanField('Активно', default=True)

    class Meta:
        ordering = ('student__last_name', 'student__first_name', 'student__username')
        verbose_name = 'Индивидуальные условия'
        verbose_name_plural = 'Индивидуальные условия'
        constraints = [
            models.UniqueConstraint(fields=('quiz', 'student'), name='unique_quiz_access_override_per_student'),
        ]

    def __str__(self):
        return f'{self.quiz.title} / {self.student}'

    def clean(self):
        if not self.quiz_id or not self.student_id:
            return
        if self.student_id and not Enrollment.objects.filter(course=self.quiz.course, student_id=self.student_id, status=EnrollmentStatus.ACTIVE).exists():
            raise ValidationError('Индивидуальные условия можно выдавать только студенту, записанному на курс.')


class QuestionType(models.TextChoices):
    SINGLE = 'single', 'Один вариант'
    MULTIPLE = 'multiple', 'Несколько вариантов'


class Question(TimeStampedModel):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Тест',
    )
    text = models.TextField('Текст вопроса')
    topic = models.CharField('Тема', max_length=120, blank=True)
    explanation = models.TextField('Пояснение к ответу', blank=True)
    question_type = models.CharField(
        'Тип вопроса',
        max_length=16,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE,
    )
    difficulty = models.CharField(
        'Сложность',
        max_length=20,
        choices=DifficultyLevel.choices,
        default=DifficultyLevel.BASIC,
    )
    points = models.PositiveIntegerField('Баллы', default=1)
    order = models.PositiveIntegerField('Порядок', default=1)

    class Meta:
        ordering = ('order', 'id')
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        constraints = [
            models.UniqueConstraint(fields=('quiz', 'order'), name='unique_question_order_per_quiz'),
        ]

    def __str__(self):
        return f'Вопрос {self.order} для {self.quiz.title}'

    @property
    def correct_choice_ids(self):
        return set(self.choices.filter(is_correct=True).values_list('id', flat=True))


class Choice(TimeStampedModel):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='choices',
        verbose_name='Вопрос',
    )
    text = models.CharField('Вариант ответа', max_length=255)
    is_correct = models.BooleanField('Правильный', default=False)
    order = models.PositiveIntegerField('Порядок', default=1)

    class Meta:
        ordering = ('order', 'id')
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответов'
        constraints = [
            models.UniqueConstraint(fields=('question', 'order'), name='unique_choice_order_per_question'),
        ]

    def __str__(self):
        return self.text

    def clean(self):
        if (
            self.is_correct
            and self.question.question_type == QuestionType.SINGLE
            and self.question.choices.exclude(pk=self.pk).filter(is_correct=True).exists()
        ):
            raise ValidationError(
                'Для вопроса с одним вариантом ответа допустим только один правильный вариант.'
            )


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = 'in_progress', 'В процессе'
    SUBMITTED = 'submitted', 'Завершена'


class Attempt(TimeStampedModel):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name='Тест',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name='Студент',
    )
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS,
    )
    started_at = models.DateTimeField('Начало', auto_now_add=True)
    submitted_at = models.DateTimeField('Завершение', null=True, blank=True)
    time_limit_minutes_snapshot = models.PositiveIntegerField('Лимит времени для попытки, мин.', default=0)
    duration_seconds = models.PositiveIntegerField('Длительность, сек.', default=0)
    score_points = models.PositiveIntegerField('Набрано баллов', default=0)
    score_percent = models.PositiveIntegerField('Результат, %', default=0)
    correct_answers_count = models.PositiveIntegerField('Правильных ответов', default=0)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Попытка'
        verbose_name_plural = 'Попытки'
        constraints = [
            models.UniqueConstraint(
                fields=('quiz', 'student'),
                condition=Q(status='in_progress'),
                name='unique_active_attempt_per_quiz',
            ),
        ]

    def __str__(self):
        return f'{self.student} / {self.quiz} / {self.get_status_display()}'

    @property
    def total_questions(self):
        return self.quiz.questions.count()

    @property
    def total_points(self):
        return self.quiz.total_points

    @property
    def is_passed(self):
        return self.status == AttemptStatus.SUBMITTED and self.score_percent >= self.quiz.passing_score

    @property
    def deadline_at(self):
        return self.started_at + timedelta(minutes=self.effective_time_limit_minutes)

    @property
    def effective_time_limit_minutes(self):
        return self.time_limit_minutes_snapshot or self.quiz.time_limit_minutes

    @property
    def duration_minutes(self):
        return round(self.duration_seconds / 60, 1) if self.duration_seconds else 0


class AttemptDraft(TimeStampedModel):
    attempt = models.OneToOneField(
        Attempt,
        on_delete=models.CASCADE,
        related_name='draft',
        verbose_name='Черновик попытки',
    )
    answers_payload = models.JSONField('Ответы', default=dict, blank=True)
    last_question_id = models.PositiveIntegerField('Последний измененный вопрос', null=True, blank=True)
    autosave_count = models.PositiveIntegerField('Число автосохранений', default=0)
    saved_at = models.DateTimeField('Сохранено', default=timezone.now)

    class Meta:
        ordering = ('-saved_at',)
        verbose_name = 'Черновик попытки'
        verbose_name_plural = 'Черновики попыток'

    def __str__(self):
        return f'Черновик попытки #{self.attempt_id}'

    @property
    def answered_questions_count(self):
        return sum(1 for choice_ids in (self.answers_payload or {}).values() if choice_ids)


class Answer(TimeStampedModel):
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='Попытка',
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='Вопрос',
    )
    selected_choices = models.ManyToManyField(
        Choice,
        related_name='answer_selections',
        blank=True,
        verbose_name='Выбранные варианты',
    )
    is_correct = models.BooleanField('Верно', default=False)
    awarded_points = models.PositiveIntegerField('Начислено баллов', default=0)

    class Meta:
        ordering = ('question__order', 'question__id')
        verbose_name = 'Ответ'
        verbose_name_plural = 'Ответы'
        constraints = [
            models.UniqueConstraint(fields=('attempt', 'question'), name='unique_answer_per_attempt_question'),
        ]

    def __str__(self):
        return f'Ответ на "{self.question}"'


class Announcement(TimeStampedModel):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='announcements',
        verbose_name='Курс',
    )
    title = models.CharField('Заголовок', max_length=200)
    body = models.TextField('Текст объявления')
    is_important = models.BooleanField('Важное объявление', default=False)
    published_at = models.DateTimeField('Дата публикации', default=timezone.now)

    class Meta:
        ordering = ('-is_important', '-published_at')
        verbose_name = 'Объявление'
        verbose_name_plural = 'Объявления'

    def __str__(self):
        return f'{self.course.title}: {self.title}'


class NotificationCategory(models.TextChoices):
    ANNOUNCEMENT = 'announcement', 'Объявление'
    QUIZ = 'quiz', 'Тест'
    ATTEMPT = 'attempt', 'Попытка'
    REVIEW = 'review', 'Проверка'
    APPEAL = 'appeal', 'Апелляция'


class UserNotification(TimeStampedModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Получатель',
    )
    category = models.CharField(
        'Категория',
        max_length=20,
        choices=NotificationCategory.choices,
    )
    title = models.CharField('Заголовок', max_length=200)
    message = models.TextField('Текст', blank=True)
    action_url = models.CharField('Ссылка', max_length=255, blank=True)
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Курс',
        null=True,
        blank=True,
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Тест',
        null=True,
        blank=True,
    )
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Попытка',
        null=True,
        blank=True,
    )
    is_read = models.BooleanField('Прочитано', default=False)
    read_at = models.DateTimeField('Прочитано в', null=True, blank=True)

    class Meta:
        ordering = ('is_read', '-created_at')
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        indexes = [
            models.Index(fields=('recipient', 'is_read', 'created_at')),
        ]

    def __str__(self):
        return f'{self.get_category_display()}: {self.title}'

    def mark_as_read(self):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=('is_read', 'read_at'))


class AttemptReview(TimeStampedModel):
    attempt = models.OneToOneField(
        Attempt,
        on_delete=models.CASCADE,
        related_name='review',
        verbose_name='Попытка',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attempt_reviews',
        verbose_name='Преподаватель',
    )
    feedback = models.TextField('Комментарий преподавателя')
    reviewed_at = models.DateTimeField('Дата проверки', default=timezone.now)

    class Meta:
        ordering = ('-reviewed_at',)
        verbose_name = 'Комментарий по попытке'
        verbose_name_plural = 'Комментарии по попыткам'

    def __str__(self):
        return f'Проверка попытки #{self.attempt_id}'


class AppealStatus(models.TextChoices):
    PENDING = 'pending', 'Ожидает решения'
    APPROVED = 'approved', 'Принята'
    REJECTED = 'rejected', 'Отклонена'


class AttemptAppeal(TimeStampedModel):
    attempt = models.OneToOneField(
        Attempt,
        on_delete=models.CASCADE,
        related_name='appeal',
        verbose_name='Попытка',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attempt_appeals',
        verbose_name='Студент',
    )
    status = models.CharField(
        'Статус апелляции',
        max_length=20,
        choices=AppealStatus.choices,
        default=AppealStatus.PENDING,
    )
    message = models.TextField('Текст апелляции')
    teacher_response = models.TextField('Ответ преподавателя', blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resolved_attempt_appeals',
        verbose_name='Рассмотрел',
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField('Рассмотрено в', null=True, blank=True)

    class Meta:
        ordering = ('status', '-created_at')
        verbose_name = 'Апелляция по попытке'
        verbose_name_plural = 'Апелляции по попыткам'

    def __str__(self):
        return f'Апелляция по попытке #{self.attempt_id}'

    def clean(self):
        if not self.attempt_id or not self.student_id:
            return
        if self.student_id and self.attempt.student_id != self.student_id:
            raise ValidationError('Апелляцию может подать только студент, которому принадлежит попытка.')
        if self.attempt.status != AttemptStatus.SUBMITTED:
            raise ValidationError('Апелляция доступна только для завершенной попытки.')
