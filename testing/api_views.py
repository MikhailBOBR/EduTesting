from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .api_serializers import (
    ApiCourseDetailSerializer,
    ApiCourseListSerializer,
    ApiQuizDetailSerializer,
    ApiStatsSerializer,
)
from .models import Announcement, Attempt, AttemptStatus, Course, Enrollment, Quiz


@extend_schema(
    summary='Сводная статистика сервиса',
    description='Возвращает агрегированные показатели для демонстрации API в Swagger и Postman.',
    responses=ApiStatsSerializer,
    examples=[
        OpenApiExample(
            'Пример ответа',
            value={
                'courses': 5,
                'quizzes': 10,
                'students': 12,
                'submitted_attempts': 66,
                'announcements': 10,
            },
        )
    ],
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
    description='Возвращает краткий перечень курсов, доступных в системе.',
)
class ApiCourseListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiCourseListSerializer

    def get_queryset(self):
        return Course.objects.filter(is_published=True).select_related('owner').order_by('title')


@extend_schema(
    summary='Детальная информация о курсе',
    description='Возвращает описание курса, опубликованные тесты и последние объявления.',
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
    summary='Детальная информация о тесте',
    description='Возвращает параметры теста, вопросы и варианты ответов без проверки ответов пользователя.',
)
class ApiQuizDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ApiQuizDetailSerializer

    def get_queryset(self):
        return Quiz.objects.filter(is_published=True, course__is_published=True).select_related('course').prefetch_related(
            'questions__choices'
        )
