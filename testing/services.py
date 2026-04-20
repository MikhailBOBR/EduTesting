from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import (
    Answer,
    AttemptDraft,
    AttemptStatus,
    Enrollment,
    EnrollmentStatus,
    NotificationCategory,
    UserNotification,
)


def normalize_answers_mapping(quiz, answers_mapping):
    normalized = {}
    questions = quiz.questions.prefetch_related('choices').all()

    for question in questions:
        raw_choice_ids = answers_mapping.get(question.id, answers_mapping.get(str(question.id), set()))
        valid_choice_ids = {choice.id for choice in question.choices.all()}
        selected_ids = set()

        for choice_id in raw_choice_ids or []:
            try:
                normalized_choice_id = int(choice_id)
            except (TypeError, ValueError):
                continue
            if normalized_choice_id in valid_choice_ids:
                selected_ids.add(normalized_choice_id)

        normalized[question.id] = selected_ids

    return normalized


def serialize_answers_mapping(answers_mapping):
    return {
        str(question_id): sorted(choice_ids)
        for question_id, choice_ids in answers_mapping.items()
        if choice_ids
    }


def get_attempt_draft_mapping(attempt):
    draft = getattr(attempt, 'draft', None)
    if draft is None:
        return {}
    return normalize_answers_mapping(attempt.quiz, draft.answers_payload or {})


@transaction.atomic
def save_attempt_draft(attempt, answers_mapping, *, last_question_id=None):
    normalized_answers = normalize_answers_mapping(attempt.quiz, answers_mapping)
    serialized_answers = serialize_answers_mapping(normalized_answers)
    valid_question_ids = set(attempt.quiz.questions.values_list('id', flat=True))
    try:
        normalized_last_question_id = int(last_question_id) if last_question_id is not None else None
    except (TypeError, ValueError):
        normalized_last_question_id = None
    if normalized_last_question_id not in valid_question_ids:
        normalized_last_question_id = None

    draft, created = AttemptDraft.objects.get_or_create(attempt=attempt)
    draft.answers_payload = serialized_answers
    draft.last_question_id = normalized_last_question_id
    draft.saved_at = timezone.now()
    draft.autosave_count = 1 if created else draft.autosave_count + 1
    draft.save(update_fields=('answers_payload', 'last_question_id', 'saved_at', 'autosave_count'))
    return draft


def clear_attempt_draft(attempt):
    AttemptDraft.objects.filter(attempt=attempt).delete()


def create_user_notification(
    recipient,
    *,
    category,
    title,
    message='',
    action_url='',
    course=None,
    quiz=None,
    attempt=None,
):
    return UserNotification.objects.create(
        recipient=recipient,
        category=category,
        title=title,
        message=message,
        action_url=action_url,
        course=course,
        quiz=quiz,
        attempt=attempt,
    )


def notify_course_students(course, *, category, title, message, action_url='', quiz=None, attempt=None, exclude_user_ids=None):
    exclude_user_ids = tuple(exclude_user_ids or ())
    enrollments = Enrollment.objects.filter(course=course, status=EnrollmentStatus.ACTIVE).select_related('student')
    if exclude_user_ids:
        enrollments = enrollments.exclude(student_id__in=exclude_user_ids)

    notifications = [
        UserNotification(
            recipient=enrollment.student,
            category=category,
            title=title,
            message=message,
            action_url=action_url,
            course=course,
            quiz=quiz,
            attempt=attempt,
        )
        for enrollment in enrollments
    ]
    if notifications:
        UserNotification.objects.bulk_create(notifications)
    return len(notifications)


def notify_announcement(announcement, *, updated=False):
    prefix = 'Обновлено объявление' if updated else 'Новое объявление'
    importance_note = 'Важное объявление.' if announcement.is_important else 'Новость по курсу.'
    return notify_course_students(
        announcement.course,
        category=NotificationCategory.ANNOUNCEMENT,
        title=f'{prefix}: {announcement.title}',
        message=f'{importance_note} Курс: {announcement.course.title}.',
        action_url=reverse('testing:course_detail', kwargs={'pk': announcement.course_id}),
    )


def notify_quiz(quiz, *, updated=False):
    prefix = 'Обновлен тест' if updated else 'Новый тест'
    availability_parts = []
    if quiz.available_from:
        availability_parts.append(f'доступен с {timezone.localtime(quiz.available_from).strftime("%d.%m %H:%M")}')
    if quiz.available_until:
        availability_parts.append(f'до {timezone.localtime(quiz.available_until).strftime("%d.%m %H:%M")}')
    availability_text = ', '.join(availability_parts) if availability_parts else 'без ограничений по окну доступа'

    return notify_course_students(
        quiz.course,
        category=NotificationCategory.QUIZ,
        title=f'{prefix}: {quiz.title}',
        message=f'Тест по курсу "{quiz.course.title}" {availability_text}.',
        action_url=reverse('testing:quiz_detail', kwargs={'pk': quiz.pk}),
        quiz=quiz,
    )


def notify_attempt_submission(attempt):
    teacher = attempt.quiz.course.owner
    student_name = attempt.student.get_full_name() or attempt.student.username
    return create_user_notification(
        teacher,
        category=NotificationCategory.ATTEMPT,
        title=f'Новая попытка: {attempt.quiz.title}',
        message=f'{student_name} завершил попытку с результатом {attempt.score_percent}%.',
        action_url=reverse('testing:attempt_result', kwargs={'pk': attempt.pk}),
        course=attempt.quiz.course,
        quiz=attempt.quiz,
        attempt=attempt,
    )


def notify_attempt_review(review, *, updated=False):
    prefix = 'Комментарий обновлен' if updated else 'Комментарий преподавателя'
    return create_user_notification(
        review.attempt.student,
        category=NotificationCategory.REVIEW,
        title=f'{prefix}: {review.attempt.quiz.title}',
        message='Преподаватель оставил обратную связь по вашей попытке.',
        action_url=reverse('testing:attempt_result', kwargs={'pk': review.attempt_id}),
        course=review.attempt.quiz.course,
        quiz=review.attempt.quiz,
        attempt=review.attempt,
    )


@transaction.atomic
def submit_attempt(attempt, answers_mapping):
    quiz = attempt.quiz
    score_points = 0
    correct_answers_count = 0
    questions = quiz.questions.prefetch_related('choices').all()
    normalized_answers = normalize_answers_mapping(quiz, answers_mapping)
    was_submitted = attempt.status == AttemptStatus.SUBMITTED

    attempt.answers.all().delete()

    for question in questions:
        selected_ids = normalized_answers.get(question.id, set())
        correct_ids = {choice.id for choice in question.choices.all() if choice.is_correct}

        answer = Answer.objects.create(attempt=attempt, question=question)
        if selected_ids:
            answer.selected_choices.set(question.choices.filter(id__in=selected_ids))

        is_correct = bool(correct_ids) and selected_ids == correct_ids
        awarded_points = question.points if is_correct else 0

        answer.is_correct = is_correct
        answer.awarded_points = awarded_points
        answer.save(update_fields=('is_correct', 'awarded_points'))

        if is_correct:
            correct_answers_count += 1
            score_points += awarded_points

    total_points = quiz.total_points
    now = timezone.now()
    duration = now - attempt.started_at
    if duration < timedelta(0):
        duration = timedelta(0)

    attempt.status = AttemptStatus.SUBMITTED
    attempt.submitted_at = now
    attempt.duration_seconds = int(duration.total_seconds())
    attempt.score_points = score_points
    attempt.score_percent = round((score_points / total_points) * 100) if total_points else 0
    attempt.correct_answers_count = correct_answers_count
    attempt.save(
        update_fields=(
            'status',
            'submitted_at',
            'duration_seconds',
            'score_points',
            'score_percent',
            'correct_answers_count',
        )
    )

    clear_attempt_draft(attempt)
    if not was_submitted:
        notify_attempt_submission(attempt)

    return attempt
