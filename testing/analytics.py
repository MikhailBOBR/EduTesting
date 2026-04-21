from django.db.models import Avg, Q

from .models import Answer, Attempt, AttemptStatus


def _normalize_topic(topic):
    topic = (topic or '').strip()
    return topic or 'Общие вопросы'


def _status_payload(accuracy_percent):
    if accuracy_percent >= 80:
        return {
            'code': 'stable',
            'label': 'Сильная зона',
            'recommendation': 'Тема усвоена стабильно. Достаточно поддерживать текущий уровень.',
        }
    if accuracy_percent >= 60:
        return {
            'code': 'watch',
            'label': 'Нужна практика',
            'recommendation': 'Есть отдельные ошибки. Полезно решить еще несколько заданий по этой теме.',
        }
    return {
        'code': 'risk',
        'label': 'Зона риска',
        'recommendation': 'Тема требует повторения. Стоит вернуться к теории и пройти контроль еще раз.',
    }


def _get_previous_submitted_attempt(attempt):
    return (
        Attempt.objects.filter(
            quiz=attempt.quiz,
            student=attempt.student,
            status=AttemptStatus.SUBMITTED,
        )
        .exclude(pk=attempt.pk)
        .filter(
            Q(submitted_at__lt=attempt.submitted_at)
            | Q(submitted_at=attempt.submitted_at, pk__lt=attempt.pk)
        )
        .order_by('-submitted_at', '-pk')
        .first()
    )


def _build_topic_rows(answer_queryset, *, include_students=False, include_attempts=False):
    topic_stats = {}

    for answer in answer_queryset:
        topic = _normalize_topic(answer.question.topic)
        stats = topic_stats.setdefault(
            topic,
            {
                'topic': topic,
                'total_questions': 0,
                'correct_answers': 0,
                'awarded_points': 0,
                'total_points': 0,
                'students': set(),
                'attempts': set(),
            },
        )
        stats['total_questions'] += 1
        stats['correct_answers'] += int(answer.is_correct)
        stats['awarded_points'] += answer.awarded_points
        stats['total_points'] += answer.question.points
        stats['students'].add(answer.attempt.student_id)
        stats['attempts'].add(answer.attempt_id)

    rows = []
    for stats in topic_stats.values():
        accuracy_percent = round((stats['correct_answers'] / stats['total_questions']) * 100) if stats['total_questions'] else 0
        points_percent = round((stats['awarded_points'] / stats['total_points']) * 100) if stats['total_points'] else 0
        status = _status_payload(accuracy_percent)
        row = {
            'topic': stats['topic'],
            'total_questions': stats['total_questions'],
            'correct_answers': stats['correct_answers'],
            'awarded_points': stats['awarded_points'],
            'total_points': stats['total_points'],
            'accuracy_percent': accuracy_percent,
            'points_percent': points_percent,
            'status_code': status['code'],
            'status_label': status['label'],
            'recommendation': status['recommendation'],
        }
        if include_students:
            row['students_count'] = len(stats['students'])
        if include_attempts:
            row['attempts_count'] = len(stats['attempts'])
        rows.append(row)

    return sorted(rows, key=lambda row: (row['accuracy_percent'], -row['total_questions'], row['topic']))


def build_attempt_topic_insights(attempt):
    topic_rows = _build_topic_rows(
        attempt.answers.select_related('question', 'attempt').all(),
    )
    weakest_topic = topic_rows[0] if topic_rows else None
    strongest_topic = max(topic_rows, key=lambda row: (row['accuracy_percent'], row['points_percent']), default=None)
    recommendations = []

    if weakest_topic and weakest_topic['status_code'] != 'stable':
        recommendations.append(
            f'Сначала повторите тему "{weakest_topic["topic"]}": {weakest_topic["recommendation"].lower()}'
        )
    if strongest_topic and strongest_topic['status_code'] == 'stable':
        recommendations.append(
            f'Тема "{strongest_topic["topic"]}" получилась лучше всего. Ее можно использовать как опору при повторении.'
        )
    if not recommendations and topic_rows:
        recommendations.append('Существенных проблем по темам не обнаружено. Можно переходить к следующему тесту.')

    return {
        'topic_rows': topic_rows,
        'weakest_topic': weakest_topic,
        'strongest_topic': strongest_topic,
        'recommendations': recommendations,
    }


def build_attempt_comparison(attempt):
    previous_attempt = _get_previous_submitted_attempt(attempt)
    if previous_attempt is None:
        return None

    current_rows = build_attempt_topic_insights(attempt)['topic_rows']
    previous_rows = build_attempt_topic_insights(previous_attempt)['topic_rows']
    current_by_topic = {row['topic']: row for row in current_rows}
    previous_by_topic = {row['topic']: row for row in previous_rows}
    topic_deltas = []

    for topic in sorted(set(previous_by_topic) | set(current_by_topic)):
        previous_row = previous_by_topic.get(topic, {})
        current_row = current_by_topic.get(topic, {})
        previous_accuracy = previous_row.get('accuracy_percent', 0)
        current_accuracy = current_row.get('accuracy_percent', 0)
        delta_accuracy = current_accuracy - previous_accuracy
        if delta_accuracy > 0:
            trend = 'up'
        elif delta_accuracy < 0:
            trend = 'down'
        else:
            trend = 'same'

        topic_deltas.append(
            {
                'topic': topic,
                'previous_accuracy': previous_accuracy,
                'current_accuracy': current_accuracy,
                'delta_accuracy': delta_accuracy,
                'trend': trend,
            }
        )

    improved_topics = sorted(
        [row for row in topic_deltas if row['delta_accuracy'] > 0],
        key=lambda row: (-row['delta_accuracy'], row['topic']),
    )
    declined_topics = sorted(
        [row for row in topic_deltas if row['delta_accuracy'] < 0],
        key=lambda row: (row['delta_accuracy'], row['topic']),
    )

    return {
        'previous_attempt': previous_attempt,
        'previous_score_percent': previous_attempt.score_percent,
        'score_delta': attempt.score_percent - previous_attempt.score_percent,
        'points_delta': attempt.score_points - previous_attempt.score_points,
        'correct_answers_delta': attempt.correct_answers_count - previous_attempt.correct_answers_count,
        'duration_delta_minutes': round((attempt.duration_seconds - previous_attempt.duration_seconds) / 60, 1),
        'improved_topics': improved_topics[:3],
        'declined_topics': declined_topics[:3],
        'unchanged_topics_count': sum(1 for row in topic_deltas if row['trend'] == 'same'),
    }


def build_attempt_integrity_flags(attempt):
    if attempt.status != AttemptStatus.SUBMITTED:
        return []

    flags = []
    effective_limit_seconds = max(attempt.effective_time_limit_minutes * 60, 60)
    fast_completion_threshold = max(300, round(effective_limit_seconds * 0.25))
    perfect_speed_threshold = max(240, round(effective_limit_seconds * 0.35))

    if attempt.score_percent == 100 and attempt.duration_seconds <= perfect_speed_threshold:
        flags.append(
            {
                'code': 'perfect_speed',
                'severity': 'high',
                'title': 'Идеальный результат за короткое время',
                'message': (
                    f'Попытка завершена за {attempt.duration_minutes} мин. '
                    f'при лимите {attempt.effective_time_limit_minutes} мин. и результате 100%.'
                ),
            }
        )
    elif attempt.score_percent >= max(attempt.quiz.passing_score, 70) and attempt.duration_seconds <= fast_completion_threshold:
        flags.append(
            {
                'code': 'fast_completion',
                'severity': 'medium',
                'title': 'Слишком быстрое завершение',
                'message': (
                    f'Попытка завершена за {attempt.duration_minutes} мин. '
                    f'при лимите {attempt.effective_time_limit_minutes} мин. и достаточно высоком результате.'
                ),
            }
        )

    previous_attempt = _get_previous_submitted_attempt(attempt)
    if previous_attempt is not None:
        score_delta = attempt.score_percent - previous_attempt.score_percent
        if score_delta >= 35 and attempt.score_percent >= max(attempt.quiz.passing_score, 70):
            flags.append(
                {
                    'code': 'sharp_improvement',
                    'severity': 'high' if score_delta >= 50 else 'medium',
                    'title': 'Резкий скачок результата',
                    'message': (
                        f'Результат вырос с {previous_attempt.score_percent}% '
                        f'до {attempt.score_percent}% за один переход между попытками.'
                    ),
                }
            )

    return flags


def summarize_integrity_flags(flags):
    if not flags:
        return {
            'risk_level': 'none',
            'risk_label': 'Нет флагов',
            'risk_score': 0,
        }

    has_high = any(flag['severity'] == 'high' for flag in flags)
    return {
        'risk_level': 'high' if has_high else 'medium',
        'risk_label': 'Высокий риск' if has_high else 'Требует внимания',
        'risk_score': sum(60 if flag['severity'] == 'high' else 35 for flag in flags),
    }


def build_course_integrity_overview(course, limit=12):
    attempts = (
        Attempt.objects.filter(
            quiz__course=course,
            status=AttemptStatus.SUBMITTED,
        )
        .select_related('student', 'quiz')
        .order_by('-submitted_at', '-pk')
    )
    rows = []
    flagged_attempts_count = 0
    high_risk_attempts_count = 0
    flagged_student_ids = set()

    for attempt in attempts:
        flags = build_attempt_integrity_flags(attempt)
        if not flags:
            continue

        summary = summarize_integrity_flags(flags)
        flagged_attempts_count += 1
        flagged_student_ids.add(attempt.student_id)
        if summary['risk_level'] == 'high':
            high_risk_attempts_count += 1

        if len(rows) < limit:
            rows.append(
                {
                    'attempt': attempt,
                    'flags': flags,
                    **summary,
                }
            )

    return {
        'flagged_attempts_count': flagged_attempts_count,
        'high_risk_attempts_count': high_risk_attempts_count,
        'students_count': len(flagged_student_ids),
        'rows': rows,
    }


def build_student_achievements(student, *, course=None):
    attempts = (
        Attempt.objects.filter(
            student=student,
            status=AttemptStatus.SUBMITTED,
        )
        .select_related('quiz', 'quiz__course')
        .order_by('submitted_at', 'pk')
    )
    if course is not None:
        attempts = attempts.filter(quiz__course=course)

    attempts = list(attempts)
    attempts_by_course = {}
    for attempt in attempts:
        attempts_by_course.setdefault(attempt.quiz.course_id, []).append(attempt)

    achievements = []
    for course_attempts in attempts_by_course.values():
        first_attempt = course_attempts[0]
        course_obj = first_attempt.quiz.course
        achievements.append(
            {
                'code': 'first_finish',
                'level': 'bronze',
                'title': 'Первый финиш',
                'description': f'Первая завершенная попытка по курсу "{course_obj.title}".',
                'awarded_at': first_attempt.submitted_at or first_attempt.created_at,
                'course': course_obj,
                'attempt': first_attempt,
            }
        )

        perfect_attempt = next((attempt for attempt in course_attempts if attempt.score_percent == 100), None)
        if perfect_attempt is not None:
            achievements.append(
                {
                    'code': 'perfect_score',
                    'level': 'gold',
                    'title': 'Идеальный результат',
                    'description': 'Получен результат 100% по одной из попыток курса.',
                    'awarded_at': perfect_attempt.submitted_at or perfect_attempt.created_at,
                    'course': course_obj,
                    'attempt': perfect_attempt,
                }
            )

        streak = []
        streak_attempt = None
        for attempt in course_attempts:
            if attempt.is_passed:
                streak.append(attempt)
                if len(streak) >= 3:
                    streak_attempt = attempt
                    break
            else:
                streak = []
        if streak_attempt is not None:
            achievements.append(
                {
                    'code': 'three_passes',
                    'level': 'silver',
                    'title': 'Серия успехов',
                    'description': 'Три подряд завершенные попытки с проходным результатом.',
                    'awarded_at': streak_attempt.submitted_at or streak_attempt.created_at,
                    'course': course_obj,
                    'attempt': streak_attempt,
                }
            )

        comeback_attempt = None
        for attempt in course_attempts:
            previous_attempt = _get_previous_submitted_attempt(attempt)
            if previous_attempt is None:
                continue
            if (
                attempt.quiz_id == previous_attempt.quiz_id
                and attempt.score_percent - previous_attempt.score_percent >= 30
                and attempt.score_percent >= max(attempt.quiz.passing_score, 70)
            ):
                comeback_attempt = attempt
                break
        if comeback_attempt is not None:
            achievements.append(
                {
                    'code': 'strong_comeback',
                    'level': 'silver',
                    'title': 'Сильный прогресс',
                    'description': 'Результат по одному из тестов заметно вырос по сравнению с предыдущей попыткой.',
                    'awarded_at': comeback_attempt.submitted_at or comeback_attempt.created_at,
                    'course': course_obj,
                    'attempt': comeback_attempt,
                }
            )

    return sorted(achievements, key=lambda item: item['awarded_at'], reverse=True)


def build_attempt_unlocked_achievements(attempt):
    achievements = build_student_achievements(attempt.student, course=attempt.quiz.course)
    return [item for item in achievements if item['attempt'].pk == attempt.pk]


def build_student_topic_diagnostics(course, student):
    answers = (
        Answer.objects.filter(
            attempt__student=student,
            attempt__quiz__course=course,
            attempt__status=AttemptStatus.SUBMITTED,
        )
        .select_related('question', 'attempt')
        .order_by('question__topic', 'question__order')
    )
    topic_rows = _build_topic_rows(answers)
    weak_topics = [row for row in topic_rows if row['status_code'] == 'risk']
    overall_accuracy = (
        round((sum(row['correct_answers'] for row in topic_rows) / sum(row['total_questions'] for row in topic_rows)) * 100)
        if topic_rows
        else 0
    )
    stable_topics_count = sum(1 for row in topic_rows if row['status_code'] == 'stable')

    recommendations = []
    if weak_topics:
        for row in weak_topics[:3]:
            recommendations.append(f'Повторите тему "{row["topic"]}" и закрепите ее дополнительной практикой.')
    elif topic_rows:
        recommendations.append('По текущим данным критических пробелов нет. Можно двигаться к следующим тестам курса.')
    else:
        recommendations.append('Диагностика появится после первой завершенной попытки по курсу.')

    return {
        'topic_rows': topic_rows,
        'weak_topics': weak_topics,
        'overall_accuracy': overall_accuracy,
        'stable_topics_count': stable_topics_count,
        'recommendations': recommendations,
    }


def build_course_topic_diagnostics(course):
    answers = (
        Answer.objects.filter(
            attempt__quiz__course=course,
            attempt__status=AttemptStatus.SUBMITTED,
        )
        .select_related('question', 'attempt')
        .order_by('question__topic', 'question__order')
    )
    topic_rows = _build_topic_rows(answers, include_students=True, include_attempts=True)
    weak_topics_count = sum(1 for row in topic_rows if row['status_code'] == 'risk')
    total_answers = sum(row['total_questions'] for row in topic_rows)
    overall_accuracy = round((sum(row['correct_answers'] for row in topic_rows) / total_answers) * 100) if total_answers else 0

    return {
        'topic_rows': topic_rows,
        'weak_topics_count': weak_topics_count,
        'total_answers': total_answers,
        'overall_accuracy': overall_accuracy,
    }


def build_course_attention_students(course):
    total_quizzes = course.quizzes.filter(is_published=True).count()
    rows = []
    enrollments = course.enrollments.select_related('student').all()

    for enrollment in enrollments:
        attempts = Attempt.objects.filter(
            student=enrollment.student,
            quiz__course=course,
            status=AttemptStatus.SUBMITTED,
        )
        average_score = round(attempts.aggregate(avg=Avg('score_percent'))['avg'] or 0)
        completed_quizzes = attempts.values('quiz').distinct().count()
        pending_quizzes = max(total_quizzes - completed_quizzes, 0)
        topic_diagnostics = build_student_topic_diagnostics(course, enrollment.student)
        weakest_topic = topic_diagnostics['weak_topics'][0]['topic'] if topic_diagnostics['weak_topics'] else None

        if total_quizzes and completed_quizzes == 0:
            status_code = 'risk'
            status_label = 'Нет попыток'
            recommendation = 'Студент еще не начал проходить тесты по курсу.'
        elif average_score >= 80 and pending_quizzes == 0:
            status_code = 'stable'
            status_label = 'Стабильно'
            recommendation = 'Студент уверенно проходит курс.'
        elif average_score >= 60 and pending_quizzes <= 1:
            status_code = 'watch'
            status_label = 'Нужно сопровождение'
            recommendation = 'Есть отдельные пробелы. Полезно дать еще практические задания.'
        else:
            status_code = 'risk'
            status_label = 'Нужна помощь'
            if weakest_topic:
                recommendation = f'Стоит уделить внимание теме "{weakest_topic}" и закрыть отставание по тестам.'
            else:
                recommendation = 'Нужно подтянуть результаты и закрыть непройденные тесты.'

        risk_score = pending_quizzes * 25 + max(70 - average_score, 0)
        if status_code == 'risk':
            risk_score += 15

        rows.append(
            {
                'student': enrollment.student,
                'completed_quizzes': completed_quizzes,
                'pending_quizzes': pending_quizzes,
                'average_score': average_score,
                'weakest_topic': weakest_topic,
                'status_code': status_code,
                'status_label': status_label,
                'recommendation': recommendation,
                'risk_score': risk_score,
            }
        )

    return sorted(rows, key=lambda row: (-row['risk_score'], row['student'].username))


def build_course_gradebook(course):
    quizzes = list(course.quizzes.filter(is_published=True).order_by('title'))
    rows = []
    enrollments = course.enrollments.select_related('student').order_by(
        'student__last_name',
        'student__first_name',
        'student__username',
    )

    for enrollment in enrollments:
        attempts = (
            Attempt.objects.filter(
                student=enrollment.student,
                quiz__course=course,
                status=AttemptStatus.SUBMITTED,
            )
            .select_related('quiz')
            .order_by('quiz__title', '-score_percent', '-submitted_at')
        )
        best_scores_by_quiz = {}
        attempt_counts_by_quiz = {}
        last_submitted_at = None

        for attempt in attempts:
            attempt_counts_by_quiz[attempt.quiz_id] = attempt_counts_by_quiz.get(attempt.quiz_id, 0) + 1
            if attempt.submitted_at and (last_submitted_at is None or attempt.submitted_at > last_submitted_at):
                last_submitted_at = attempt.submitted_at

            current_best = best_scores_by_quiz.get(attempt.quiz_id)
            if current_best is None or attempt.score_percent > current_best:
                best_scores_by_quiz[attempt.quiz_id] = attempt.score_percent

        completed_quizzes = len(best_scores_by_quiz)
        pending_quizzes = max(len(quizzes) - completed_quizzes, 0)
        average_score = round(sum(best_scores_by_quiz.values()) / completed_quizzes) if completed_quizzes else 0
        best_score = max(best_scores_by_quiz.values()) if best_scores_by_quiz else 0
        progress_percent = round((completed_quizzes / len(quizzes)) * 100) if quizzes else 0

        rows.append(
            {
                'student': enrollment.student,
                'enrollment': enrollment,
                'average_score': average_score,
                'best_score': best_score,
                'completed_quizzes': completed_quizzes,
                'pending_quizzes': pending_quizzes,
                'progress_percent': progress_percent,
                'quiz_scores': {quiz.id: best_scores_by_quiz.get(quiz.id) for quiz in quizzes},
                'quiz_attempt_counts': {quiz.id: attempt_counts_by_quiz.get(quiz.id, 0) for quiz in quizzes},
                'last_submitted_at': last_submitted_at,
            }
        )

    return {
        'quizzes': quizzes,
        'rows': rows,
    }


def build_course_leaderboard(course, limit=10):
    gradebook = build_course_gradebook(course)
    ranking = sorted(
        gradebook['rows'],
        key=lambda row: (-row['average_score'], -row['completed_quizzes'], row['pending_quizzes'], row['student'].username),
    )
    leaderboard = []

    for index, row in enumerate(ranking[:limit], start=1):
        if row['progress_percent'] == 100 and row['average_score'] >= 85:
            status_code = 'leader'
            status_label = 'Лидер курса'
        elif row['average_score'] >= 70:
            status_code = 'stable'
            status_label = 'Стабильный темп'
        elif row['completed_quizzes'] == 0:
            status_code = 'risk'
            status_label = 'Нет прогресса'
        else:
            status_code = 'watch'
            status_label = 'Нужно усиление'

        leaderboard.append(
            {
                **row,
                'rank': index,
                'status_code': status_code,
                'status_label': status_label,
            }
        )

    return leaderboard
