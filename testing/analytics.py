from django.db.models import Avg

from .models import Answer, Attempt, AttemptStatus, Enrollment


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
    overall_accuracy = round((sum(row['correct_answers'] for row in topic_rows) / sum(row['total_questions'] for row in topic_rows)) * 100) if topic_rows else 0
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
