from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.security import (
    get_client_ip,
    get_login_lockout_remaining_seconds,
    register_failed_login,
    reset_failed_logins,
)

from .analytics import (
    build_attempt_comparison,
    build_attempt_integrity_flags,
    build_attempt_unlocked_achievements,
    build_course_integrity_overview,
    build_attempt_topic_insights,
    build_course_attention_students,
    build_course_leaderboard,
    build_course_topic_diagnostics,
    build_student_achievements,
)
from .api_serializers import (
    ApiAttemptAppealRequestSerializer,
    ApiAttemptAppealReviewRequestSerializer,
    ApiAttemptAppealSerializer,
    ApiAttemptDraftSaveRequestSerializer,
    ApiAttemptDraftSerializer,
    ApiAttemptDetailSerializer,
    ApiAttemptStartResponseSerializer,
    ApiAttemptSubmitRequestSerializer,
    ApiAttemptSummarySerializer,
    ApiCourseAnalyticsSerializer,
    ApiCourseDetailSerializer,
    ApiCourseIntegritySerializer,
    ApiCourseListSerializer,
    ApiEnrollmentResponseSerializer,
    ApiMyCourseSerializer,
    ApiPasswordChangeRequestSerializer,
    ApiPasswordChangeResponseSerializer,
    ApiQuizAccessOverrideRequestSerializer,
    ApiQuizAccessOverrideSerializer,
    ApiQuizAttemptsResponseSerializer,
    ApiQuizAttemptListSerializer,
    ApiQuizDetailSerializer,
    ApiStatsSerializer,
    ApiStudentAchievementSerializer,
    ApiTokenRequestSerializer,
    ApiTokenResponseSerializer,
    ApiUserSerializer,
)
from .models import (
    Announcement,
    AppealStatus,
    Attempt,
    AttemptAppeal,
    AttemptStatus,
    Course,
    Enrollment,
    EnrollmentStatus,
    Quiz,
    QuizAccessOverride,
)
from .services import (
    notify_attempt_appeal,
    notify_attempt_appeal_resolution,
    notify_quiz_override,
    save_attempt_draft,
    submit_attempt,
)


def serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.get_full_name() or user.username,
        'role': user.role,
        'email': user.email,
        'academic_group': user.academic_group,
    }


def serialize_achievement(achievement):
    return {
        **achievement,
        'attempt_id': achievement['attempt'].pk,
        'course': achievement['course'],
    }


def ensure_student(user):
    if not user.is_student:
        raise PermissionDenied('Эндпоинт доступен только студенту.')


def ensure_course_owner(user, course):
    if not user.is_teacher or course.owner_id != user.id:
        raise PermissionDenied('Эндпоинт доступен только преподавателю этого курса.')


def build_attempt_payload(attempt, user):
    show_answer_key = user.is_teacher or attempt.quiz.show_correct_answers
    integrity_flags = build_attempt_integrity_flags(attempt) if user.is_teacher else []
    unlocked_achievements = [serialize_achievement(item) for item in build_attempt_unlocked_achievements(attempt)]
    answers_payload = []
    answers = (
        attempt.answers.select_related('question')
        .prefetch_related('selected_choices', 'question__choices')
        .all()
    )
    for answer in answers:
        correct_choices = [choice for choice in answer.question.choices.all() if choice.is_correct]
        answers_payload.append(
            {
                'question_id': answer.question_id,
                'question_text': answer.question.text,
                'topic': answer.question.topic or '',
                'is_correct': answer.is_correct,
                'awarded_points': answer.awarded_points,
                'selected_choice_ids': [choice.id for choice in answer.selected_choices.all()],
                'selected_choices': [choice.text for choice in answer.selected_choices.all()],
                'correct_choice_ids': [choice.id for choice in correct_choices] if show_answer_key else [],
                'correct_choices': [choice.text for choice in correct_choices] if show_answer_key else [],
            }
        )

    topic_insights = build_attempt_topic_insights(attempt)
    comparison = build_attempt_comparison(attempt)
    payload = {
        'attempt': attempt,
        'answers': answers_payload,
        'topic_insights': topic_insights['topic_rows'],
        'recommendations': topic_insights['recommendations'],
        'review': getattr(attempt, 'review', None),
        'appeal': getattr(attempt, 'appeal', None),
        'show_answer_key': show_answer_key,
        'integrity_flags': integrity_flags,
        'new_achievements': unlocked_achievements,
        'comparison': {
            **comparison,
            'previous_attempt_id': comparison['previous_attempt'].pk,
            'previous_submitted_at': comparison['previous_attempt'].submitted_at,
        }
        if comparison
        else None,
    }
    return ApiAttemptDetailSerializer(payload).data


@extend_schema(
    summary='Получение токена авторизации',
    description=(
        'Авторизует пользователя по логину и паролю и возвращает токен для дальнейшей '
        'работы в Postman и Swagger. После серии неудачных попыток вход временно '
        'блокируется для защиты от перебора паролей.'
    ),
    request=ApiTokenRequestSerializer,
    responses={200: ApiTokenResponseSerializer},
    examples=[
        OpenApiExample(
            'Пример запроса',
            value={'username': 'student_demo', 'password': 'StudentDemo123!'},
            request_only=True,
        )
    ],
)
class ApiTokenAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = ApiTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']
        ip_address = get_client_ip(request)
        remaining = get_login_lockout_remaining_seconds(username, ip_address)
        if remaining > 0:
            raise ValidationError(
                {'detail': f'Слишком много неудачных попыток входа. Повторите через {remaining} сек.'}
            )

        user = authenticate(
            request=request,
            username=username,
            password=serializer.validated_data['password'],
        )
        if user is None:
            state = register_failed_login(username, ip_address)
            if state.get('blocked_until'):
                remaining = get_login_lockout_remaining_seconds(username, ip_address)
                raise ValidationError(
                    {'detail': f'Слишком много неудачных попыток входа. Повторите через {remaining} сек.'}
                )
            raise ValidationError({'detail': 'Неверный логин или пароль.'})

        reset_failed_logins(username, ip_address)
        token, _ = Token.objects.get_or_create(user=user)
        payload = {
            'token': token.key,
            'user': serialize_user(user),
        }
        return Response(ApiTokenResponseSerializer(payload).data)


@extend_schema(
    summary='Информация о текущем пользователе',
    description='Возвращает профиль авторизованного пользователя с ролью, почтой и учебной группой.',
    responses={200: ApiUserSerializer},
)
class ApiMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(ApiUserSerializer(serialize_user(request.user)).data)


@extend_schema(
    summary='Смена пароля',
    description=(
        'Позволяет авторизованному пользователю сменить пароль через API. '
        'Новый пароль проходит стандартную валидацию Django, а после успешной смены '
        'выдается новый токен для дальнейшей работы в Postman и Swagger.'
    ),
    request=ApiPasswordChangeRequestSerializer,
    responses={200: ApiPasswordChangeResponseSerializer},
    examples=[
        OpenApiExample(
            'Пример смены пароля',
            value={
                'current_password': 'StudentDemo123!',
                'new_password': 'StudentDemo456!',
                'new_password_confirm': 'StudentDemo456!',
            },
            request_only=True,
        ),
        OpenApiExample(
            'Пример ответа',
            value={
                'detail': 'Пароль обновлен. Используйте новый токен для API-запросов.',
                'token': '0123456789abcdef0123456789abcdef01234567',
            },
            response_only=True,
        ),
    ],
)
class ApiPasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ApiPasswordChangeRequestSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=('password',))

        reset_failed_logins(user.username, get_client_ip(request))
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        payload = {
            'detail': 'Пароль обновлен. Используйте новый токен для API-запросов.',
            'token': token.key,
        }
        return Response(ApiPasswordChangeResponseSerializer(payload).data)


@extend_schema(
    summary='Сводная статистика сервиса',
    description='Возвращает агрегированные показатели для демонстрации API в Swagger и Postman.',
    responses=ApiStatsSerializer,
)
class ApiStatsView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ApiStatsSerializer

    def get(self, request, *args, **kwargs):
        payload = {
            'courses': Course.objects.filter(is_published=True).count(),
            'quizzes': Quiz.objects.filter(is_published=True, course__is_published=True).count(),
            'students': Enrollment.objects.values('student').distinct().count(),
            'submitted_attempts': Attempt.objects.filter(status=AttemptStatus.SUBMITTED).count(),
            'announcements': Announcement.objects.filter(course__is_published=True).count(),
        }
        return Response(self.serializer_class(payload).data)


@extend_schema(
    summary='Список опубликованных курсов',
    description='Публичный каталог курсов с краткой информацией, владельцем и количеством опубликованных тестов.',
)
class ApiCourseListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiCourseListSerializer

    def get_queryset(self):
        return Course.objects.filter(is_published=True).select_related('owner').order_by('title')


@extend_schema(
    summary='Мои курсы',
    description='Для студента возвращает курсы по записи, для преподавателя — управляемые курсы.',
)
class ApiMyCourseListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ApiMyCourseSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_teacher:
            return Course.objects.filter(owner=user).select_related('owner').order_by('title')
        return (
            Course.objects.filter(enrollments__student=user, is_published=True)
            .select_related('owner')
            .distinct()
            .order_by('title')
        )


@extend_schema(
    summary='Мои достижения',
    description='Возвращает вычисляемые достижения текущего пользователя: первые завершенные попытки, идеальные результаты, серии успешных прохождений и сильный прогресс.',
    responses={200: ApiStudentAchievementSerializer(many=True)},
)
class ApiMyAchievementsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        achievements = [serialize_achievement(item) for item in build_student_achievements(request.user)]
        return Response(ApiStudentAchievementSerializer(achievements, many=True).data)


@extend_schema(
    summary='Детальная информация о курсе',
    description='Возвращает полное описание курса, список опубликованных тестов и объявления.',
)
class ApiCourseDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiCourseDetailSerializer

    def get_queryset(self):
        return Course.objects.filter(is_published=True).select_related('owner').prefetch_related(
            'quizzes',
            'announcements',
        )


@extend_schema(
    summary='Запись студента на курс',
    description='Создает запись студента на опубликованный курс или подтверждает, что запись уже существует.',
    responses={200: ApiEnrollmentResponseSerializer},
)
class ApiCourseEnrollView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ApiEnrollmentResponseSerializer

    def post(self, request, pk, *args, **kwargs):
        ensure_student(request.user)
        course = get_object_or_404(Course, pk=pk, is_published=True)
        enrollment, created = Enrollment.objects.get_or_create(course=course, student=request.user)
        payload = {
            'course': course,
            'enrolled': True,
            'status': enrollment.status,
        }
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(ApiEnrollmentResponseSerializer(payload).data, status=response_status)


@extend_schema(
    summary='Аналитика курса для преподавателя',
    description='Сводит общую точность по курсу, слабые темы, студентов с рисками и лидерборд.',
    responses={200: ApiCourseAnalyticsSerializer},
)
class ApiCourseAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        course = get_object_or_404(Course.objects.select_related('owner'), pk=pk)
        ensure_course_owner(request.user, course)

        topic_diagnostics = build_course_topic_diagnostics(course)
        attention_students = build_course_attention_students(course)
        leaderboard = build_course_leaderboard(course)
        payload = {
            'course': course,
            'overall_accuracy': topic_diagnostics['overall_accuracy'],
            'weak_topics_count': topic_diagnostics['weak_topics_count'],
            'total_answers': topic_diagnostics['total_answers'],
            'topic_rows': topic_diagnostics['topic_rows'],
            'attention_students': [
                {
                    **row,
                    'student': serialize_user(row['student']),
                }
                for row in attention_students
            ],
            'leaderboard': [
                {
                    **row,
                    'student': serialize_user(row['student']),
                }
                for row in leaderboard
            ],
        }
        return Response(ApiCourseAnalyticsSerializer(payload).data)


@extend_schema(
    summary='Контроль подозрительных попыток по курсу',
    description='Возвращает попытки с дополнительными флагами внимания: слишком быстрое завершение, идеальный результат за короткое время и резкий скачок между попытками.',
    responses={200: ApiCourseIntegritySerializer},
)
class ApiCourseIntegrityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        course = get_object_or_404(Course.objects.select_related('owner'), pk=pk)
        ensure_course_owner(request.user, course)
        integrity = build_course_integrity_overview(course)
        payload = {
            'course': course,
            'flagged_attempts_count': integrity['flagged_attempts_count'],
            'high_risk_attempts_count': integrity['high_risk_attempts_count'],
            'students_count': integrity['students_count'],
            'attempts': [
                {
                    'attempt_id': row['attempt'].pk,
                    'submitted_at': row['attempt'].submitted_at,
                    'score_percent': row['attempt'].score_percent,
                    'duration_minutes': row['attempt'].duration_minutes,
                    'risk_level': row['risk_level'],
                    'risk_label': row['risk_label'],
                    'student': serialize_user(row['attempt'].student),
                    'quiz': row['attempt'].quiz,
                    'flags': row['flags'],
                }
                for row in integrity['rows']
            ],
        }
        return Response(ApiCourseIntegritySerializer(payload).data)


@extend_schema(
    summary='Детальная информация о тесте',
    description='Возвращает описание теста, вопросы, настройки доступности и эффективные ограничения для текущего пользователя.',
)
class ApiQuizDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiQuizDetailSerializer

    def get_queryset(self):
        return Quiz.objects.filter(is_published=True, course__is_published=True).select_related('course').prefetch_related(
            'questions__choices'
        )


@extend_schema(
    summary='Старт попытки по тесту',
    description='Создает новую попытку или переиспользует уже активную, если студент не завершил предыдущее прохождение.',
    responses={200: ApiAttemptStartResponseSerializer, 201: ApiAttemptStartResponseSerializer},
)
class ApiQuizStartView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ApiAttemptStartResponseSerializer

    def post(self, request, pk, *args, **kwargs):
        ensure_student(request.user)
        quiz = get_object_or_404(
            Quiz.objects.select_related('course').prefetch_related('questions__choices'),
            pk=pk,
            is_published=True,
            course__is_published=True,
        )

        if not Enrollment.objects.filter(course=quiz.course, student=request.user).exists():
            raise ValidationError({'detail': 'Сначала нужно записаться на курс.'})
        if not quiz.is_available:
            raise ValidationError({'detail': 'Тест сейчас недоступен для прохождения.'})
        if not quiz.questions.exists():
            raise ValidationError({'detail': 'В тесте пока нет вопросов.'})
        if quiz.unanswered_configuration_count:
            raise ValidationError({'detail': 'Тест еще не полностью настроен преподавателем.'})

        attempt = Attempt.objects.filter(
            quiz=quiz,
            student=request.user,
            status=AttemptStatus.IN_PROGRESS,
        ).first()
        reused_existing = attempt is not None

        if attempt is None:
            if quiz.remaining_attempts(request.user) <= 0:
                raise ValidationError({'detail': 'Лимит попыток исчерпан.'})
            attempt = Attempt.objects.create(
                quiz=quiz,
                student=request.user,
                time_limit_minutes_snapshot=quiz.get_effective_time_limit(request.user),
            )

        payload = {
            'attempt': attempt,
            'reused_existing': reused_existing,
        }
        response_status = status.HTTP_200_OK if reused_existing else status.HTTP_201_CREATED
        return Response(ApiAttemptStartResponseSerializer(payload).data, status=response_status)


@extend_schema(
    summary='Список попыток по тесту для преподавателя',
    description='Возвращает журнал завершенных попыток с краткой сводкой по результату и индикаторам integrity-контроля.',
    responses={200: ApiQuizAttemptsResponseSerializer},
)
class ApiQuizAttemptsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        quiz = get_object_or_404(Quiz.objects.select_related('course', 'course__owner'), pk=pk)
        ensure_course_owner(request.user, quiz.course)
        attempts = list(
            Attempt.objects.filter(quiz=quiz, status=AttemptStatus.SUBMITTED)
            .select_related('student', 'review')
            .order_by('-submitted_at')
        )
        for attempt in attempts:
            flags = build_attempt_integrity_flags(attempt)
            attempt.integrity_flags_count = len(flags)
            attempt.highest_integrity_severity = 'high' if any(flag['severity'] == 'high' for flag in flags) else ('medium' if flags else '')
        payload = {
            'quiz': quiz,
            'attempts': attempts,
        }
        return Response(ApiQuizAttemptsResponseSerializer(payload).data)


class ApiQuizOverrideListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_quiz(self, pk):
        quiz = get_object_or_404(Quiz.objects.select_related('course', 'course__owner'), pk=pk)
        ensure_course_owner(self.request.user, quiz.course)
        return quiz

    @extend_schema(
        summary='Список индивидуальных условий по тесту',
        description='Показывает все персональные условия по тесту для студентов курса.',
        responses={200: ApiQuizAccessOverrideSerializer(many=True)},
    )
    def get(self, request, pk, *args, **kwargs):
        quiz = self.get_quiz(pk)
        overrides = (
            QuizAccessOverride.objects.filter(quiz=quiz)
            .select_related('student')
            .order_by('-is_active', 'student__last_name', 'student__first_name', 'student__username')
        )
        return Response(ApiQuizAccessOverrideSerializer(overrides, many=True).data)

    @extend_schema(
        summary='Создание или обновление индивидуальных условий',
        description='Позволяет преподавателю выдать студенту дополнительные попытки, время и комментарий по тесту.',
        request=ApiQuizAccessOverrideRequestSerializer,
        responses={200: ApiQuizAccessOverrideSerializer, 201: ApiQuizAccessOverrideSerializer},
        examples=[
            OpenApiExample(
                'Пример индивидуальных условий',
                value={
                    'student_id': 6,
                    'extra_time_minutes': 15,
                    'extra_attempts': 1,
                    'notes': 'Индивидуальные условия для демонстрации API.',
                    'is_active': True,
                },
                request_only=True,
            )
        ],
    )
    def post(self, request, pk, *args, **kwargs):
        quiz = self.get_quiz(pk)
        serializer = ApiQuizAccessOverrideRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        enrollment = get_object_or_404(
            Enrollment.objects.select_related('student'),
            course=quiz.course,
            student_id=serializer.validated_data['student_id'],
            status=EnrollmentStatus.ACTIVE,
        )
        override, created = QuizAccessOverride.objects.update_or_create(
            quiz=quiz,
            student=enrollment.student,
            defaults={
                'extra_time_minutes': serializer.validated_data.get('extra_time_minutes', 0),
                'extra_attempts': serializer.validated_data.get('extra_attempts', 0),
                'notes': serializer.validated_data.get('notes', ''),
                'is_active': serializer.validated_data.get('is_active', True),
            },
        )
        notify_quiz_override(override, updated=not created)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(ApiQuizAccessOverrideSerializer(override).data, status=response_status)


@extend_schema(
    summary='Детальная информация о попытке',
    description='Возвращает подробный результат попытки: ответы, рекомендации, сравнение, апелляцию, review и новые достижения.',
    responses={200: ApiAttemptDetailSerializer},
)
class ApiAttemptDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student').prefetch_related(
                'answers__selected_choices',
                'answers__question__choices',
            ),
            pk=pk,
        )
        user = request.user
        if attempt.student_id != user.id and not (user.is_teacher and attempt.quiz.course.owner_id == user.id):
            raise PermissionDenied('Нет доступа к этой попытке.')
        return Response(build_attempt_payload(attempt, user))


@extend_schema(
    summary='Подача апелляции по попытке',
    description='Создает новую апелляцию по завершенной попытке или обновляет текст еще не рассмотренной апелляции.',
    request=ApiAttemptAppealRequestSerializer,
    responses={200: ApiAttemptAppealSerializer, 201: ApiAttemptAppealSerializer},
    examples=[
        OpenApiExample(
            'Пример апелляции',
            value={
                'message': 'Прошу пересмотреть результат по одному из вопросов, так как ответ частично совпадает с эталоном.',
            },
            request_only=True,
        )
    ],
)
class ApiAttemptAppealView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student'),
            pk=pk,
        )
        ensure_student(request.user)
        if attempt.student_id != request.user.id:
            raise PermissionDenied('Можно подать апелляцию только по своей попытке.')
        if attempt.status != AttemptStatus.SUBMITTED:
            raise ValidationError({'detail': 'Апелляция доступна только для завершенной попытки.'})

        serializer = ApiAttemptAppealRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        appeal, created = AttemptAppeal.objects.get_or_create(
            attempt=attempt,
            defaults={
                'student': request.user,
                'message': serializer.validated_data['message'],
            },
        )
        if not created and appeal.status != AppealStatus.PENDING:
            raise ValidationError({'detail': 'Апелляция уже рассмотрена преподавателем.'})

        if not created:
            appeal.message = serializer.validated_data['message']
            appeal.teacher_response = ''
            appeal.resolved_by = None
            appeal.resolved_at = None
            appeal.status = AppealStatus.PENDING
            appeal.save(update_fields=('message', 'teacher_response', 'resolved_by', 'resolved_at', 'status', 'updated_at'))

        notify_attempt_appeal(appeal, updated=not created)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(ApiAttemptAppealSerializer(appeal).data, status=response_status)


@extend_schema(
    summary='Рассмотрение апелляции преподавателем',
    description='Позволяет преподавателю принять, отклонить или вернуть апелляцию в статус ожидания.',
    request=ApiAttemptAppealReviewRequestSerializer,
    responses={200: ApiAttemptAppealSerializer},
    examples=[
        OpenApiExample(
            'Пример решения по апелляции',
            value={
                'status': 'rejected',
                'teacher_response': 'Результат оставлен без изменения, так как критерий требует полного совпадения ответа.',
            },
            request_only=True,
        )
    ],
)
class ApiAttemptAppealReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        appeal = get_object_or_404(
            AttemptAppeal.objects.select_related('attempt', 'attempt__quiz', 'attempt__quiz__course', 'student'),
            pk=pk,
        )
        ensure_course_owner(request.user, appeal.attempt.quiz.course)

        serializer = ApiAttemptAppealReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        appeal.status = serializer.validated_data['status']
        appeal.teacher_response = serializer.validated_data.get('teacher_response', '')
        if appeal.status == AppealStatus.PENDING:
            appeal.resolved_by = None
            appeal.resolved_at = None
        else:
            appeal.resolved_by = request.user
            appeal.resolved_at = timezone.now()
        appeal.save(update_fields=('status', 'teacher_response', 'resolved_by', 'resolved_at', 'updated_at'))

        if appeal.status != AppealStatus.PENDING:
            notify_attempt_appeal_resolution(appeal)
        return Response(ApiAttemptAppealSerializer(appeal).data)


@extend_schema(
    summary='Автосохранение черновика попытки',
    description='Сохраняет промежуточные ответы студента и последнюю активную позицию в тесте.',
    request=ApiAttemptDraftSaveRequestSerializer,
    responses={200: ApiAttemptDraftSerializer},
    examples=[
        OpenApiExample(
            'Пример черновика',
            value={
                'answers': {'1': [2]},
                'last_question_id': 1,
            },
            request_only=True,
        )
    ],
)
class ApiAttemptDraftSaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student').prefetch_related('quiz__questions__choices'),
            pk=pk,
        )
        ensure_student(request.user)
        if attempt.student_id != request.user.id:
            raise PermissionDenied('Можно сохранять только свои черновики.')
        if attempt.status == AttemptStatus.SUBMITTED:
            raise ValidationError({'detail': 'Нельзя сохранять черновик для завершенной попытки.'})

        serializer = ApiAttemptDraftSaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = save_attempt_draft(
            attempt,
            serializer.validated_data['answers'],
            last_question_id=serializer.validated_data.get('last_question_id'),
        )
        payload = {
            'saved_at': draft.saved_at,
            'autosave_count': draft.autosave_count,
            'answered_questions_count': draft.answered_questions_count,
            'last_question_id': draft.last_question_id,
        }
        return Response(ApiAttemptDraftSerializer(payload).data)

@extend_schema(
    summary='Отправка попытки на проверку',
    description='Завершает попытку, проверяет ответы и возвращает подробный результат с аналитикой и дополнительными блоками.',
    request=ApiAttemptSubmitRequestSerializer,
    responses={200: ApiAttemptDetailSerializer},
    examples=[
        OpenApiExample(
            'Пример тела запроса',
            value={'answers': {'1': [2], '2': [4, 6]}},
            request_only=True,
        )
    ],
)
class ApiAttemptSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student').prefetch_related('quiz__questions__choices'),
            pk=pk,
        )
        ensure_student(request.user)
        if attempt.student_id != request.user.id:
            raise PermissionDenied('Можно отправлять только свои попытки.')
        if attempt.status == AttemptStatus.SUBMITTED:
            raise ValidationError({'detail': 'Попытка уже завершена.'})

        serializer = ApiAttemptSubmitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submit_attempt(attempt, serializer.validated_data['answers'])
        attempt.refresh_from_db()

        return Response(build_attempt_payload(attempt, request.user))

