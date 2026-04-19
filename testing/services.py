from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Answer, AttemptStatus


@transaction.atomic
def submit_attempt(attempt, answers_mapping):
    quiz = attempt.quiz
    score_points = 0
    correct_answers_count = 0
    questions = quiz.questions.prefetch_related('choices').all()

    attempt.answers.all().delete()

    for question in questions:
        selected_ids = set(answers_mapping.get(question.id, set()))
        valid_ids = {choice.id for choice in question.choices.all()}
        selected_ids &= valid_ids
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

    return attempt
