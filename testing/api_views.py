from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .analytics import (
    build_attempt_comparison,
    build_attempt_topic_insights,
    build_course_attention_students,
    build_course_leaderboard,
    build_course_topic_diagnostics,
)
from .api_serializers import (
    ApiAttemptDraftSaveRequestSerializer,
    ApiAttemptDraftSerializer,
    ApiAttemptDetailSerializer,
    ApiAttemptStartResponseSerializer,
    ApiAttemptSubmitRequestSerializer,
    ApiAttemptSummarySerializer,
    ApiCourseAnalyticsSerializer,
    ApiCourseDetailSerializer,
    ApiCourseListSerializer,
    ApiEnrollmentResponseSerializer,
    ApiMyCourseSerializer,
    ApiQuizAttemptsResponseSerializer,
    ApiQuizAttemptListSerializer,
    ApiQuizDetailSerializer,
    ApiStatsSerializer,
    ApiTokenRequestSerializer,
    ApiTokenResponseSerializer,
    ApiUserSerializer,
)
from .models import Announcement, Attempt, AttemptStatus, Course, Enrollment, Quiz
from .services import save_attempt_draft, submit_attempt


def serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.get_full_name() or user.username,
        'role': user.role,
        'email': user.email,
        'academic_group': user.academic_group,
    }


def ensure_student(user):
    if not user.is_student:
        raise PermissionDenied('Эндпоинт доступен только студенту.')


def ensure_course_owner(user, course):
    if not user.is_teacher or course.owner_id != user.id:
        raise PermissionDenied('Эндпоинт доступен только преподавателю этого курса.')


def build_attempt_payload(attempt, user):
    show_answer_key = user.is_teacher or attempt.quiz.show_correct_answers
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
        'show_answer_key': show_answer_key,
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
    description='Авторизует пользователя по логину и паролю и возвращает токен для дальнейшей работы в Postman и Swagger.',
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
        user = authenticate(
            request=request,
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if user is None:
            raise ValidationError({'detail': 'Неверный логин или пароль.'})

        token, _ = Token.objects.get_or_create(user=user)
        payload = {
            'token': token.key,
            'user': serialize_user(user),
        }
        return Response(ApiTokenResponseSerializer(payload).data)


@extend_schema(summary='Информация о текущем пользователе', responses={200: ApiUserSerializer})
class ApiMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(ApiUserSerializer(serialize_user(request.user)).data)


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


@extend_schema(summary='Список опубликованных курсов')
class ApiCourseListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiCourseListSerializer

    def get_queryset(self):
        return Course.objects.filter(is_published=True).select_related('owner').order_by('title')


@extend_schema(summary='Мои курсы', description='Для студента возвращает курсы по записи, для преподавателя — управляемые курсы.')
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


@extend_schema(summary='Детальная информация о курсе')
class ApiCourseDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiCourseDetailSerializer

    def get_queryset(self):
        return Course.objects.filter(is_published=True).select_related('owner').prefetch_related(
            'quizzes',
            'announcements',
        )


@extend_schema(summary='Запись студента на курс', responses={200: ApiEnrollmentResponseSerializer})
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


@extend_schema(summary='Аналитика курса для преподавателя', responses={200: ApiCourseAnalyticsSerializer})
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


@extend_schema(summary='Детальная информация о тесте')
class ApiQuizDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiQuizDetailSerializer

    def get_queryset(self):
        return Quiz.objects.filter(is_published=True, course__is_published=True).select_related('course').prefetch_related(
            'questions__choices'
        )


@extend_schema(summary='Старт попытки по тесту', responses={200: ApiAttemptStartResponseSerializer, 201: ApiAttemptStartResponseSerializer})
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
            attempt = Attempt.objects.create(quiz=quiz, student=request.user)

        payload = {
            'attempt': attempt,
            'reused_existing': reused_existing,
        }
        response_status = status.HTTP_200_OK if reused_existing else status.HTTP_201_CREATED
        return Response(ApiAttemptStartResponseSerializer(payload).data, status=response_status)


@extend_schema(summary='Список попыток по тесту для преподавателя', responses={200: ApiQuizAttemptsResponseSerializer})
class ApiQuizAttemptsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        quiz = get_object_or_404(Quiz.objects.select_related('course', 'course__owner'), pk=pk)
        ensure_course_owner(request.user, quiz.course)
        attempts = (
            Attempt.objects.filter(quiz=quiz, status=AttemptStatus.SUBMITTED)
            .select_related('student', 'review')
            .order_by('-submitted_at')
        )
        payload = {
            'quiz': quiz,
            'attempts': attempts,
        }
        return Response(ApiQuizAttemptsResponseSerializer(payload).data)


@extend_schema(summary='Детальная информация о попытке', responses={200: ApiAttemptDetailSerializer})
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
    summary='Автосохранение черновика попытки',
    request=ApiAttemptDraftSaveRequestSerializer,
    responses={200: ApiAttemptDraftSerializer},
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
