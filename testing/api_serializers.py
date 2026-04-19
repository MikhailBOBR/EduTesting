from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Announcement, Choice, Course, Question, Quiz


class ApiAnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ('id', 'title', 'body', 'is_important', 'published_at')


class ApiStatsSerializer(serializers.Serializer):
    courses = serializers.IntegerField()
    quizzes = serializers.IntegerField()
    students = serializers.IntegerField()
    submitted_attempts = serializers.IntegerField()
    announcements = serializers.IntegerField()


class ApiCourseReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ('id', 'title', 'subject_code')


class ApiQuizSummarySerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(read_only=True)
    total_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quiz
        fields = (
            'id',
            'title',
            'description',
            'time_limit_minutes',
            'passing_score',
            'max_attempts',
            'question_count',
            'total_points',
            'is_published',
        )


class ApiCourseListSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    published_quizzes_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = (
            'id',
            'title',
            'subject_code',
            'summary',
            'semester',
            'academic_year',
            'owner_name',
            'published_quizzes_count',
        )

    @extend_schema_field(serializers.CharField())
    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.username


class ApiCourseDetailSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    total_students = serializers.IntegerField(read_only=True)
    average_score = serializers.IntegerField(read_only=True)
    completion_rate = serializers.IntegerField(read_only=True)
    quizzes = serializers.SerializerMethodField()
    announcements = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            'id',
            'title',
            'subject_code',
            'summary',
            'description',
            'audience',
            'semester',
            'academic_year',
            'assessment_policy',
            'owner_name',
            'total_students',
            'average_score',
            'completion_rate',
            'quizzes',
            'announcements',
        )

    @extend_schema_field(serializers.CharField())
    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.username

    @extend_schema_field(ApiQuizSummarySerializer(many=True))
    def get_quizzes(self, obj):
        quizzes = obj.quizzes.filter(is_published=True)
        return ApiQuizSummarySerializer(quizzes, many=True).data

    @extend_schema_field(ApiAnnouncementSerializer(many=True))
    def get_announcements(self, obj):
        announcements = obj.announcements.all()[:5]
        return ApiAnnouncementSerializer(announcements, many=True).data


class ApiChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ('id', 'text', 'order')


class ApiQuestionSerializer(serializers.ModelSerializer):
    choices = ApiChoiceSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = (
            'id',
            'text',
            'topic',
            'question_type',
            'difficulty',
            'points',
            'order',
            'choices',
        )


class ApiQuizDetailSerializer(serializers.ModelSerializer):
    course = serializers.SerializerMethodField()
    question_count = serializers.IntegerField(read_only=True)
    total_points = serializers.IntegerField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    questions = ApiQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = (
            'id',
            'title',
            'description',
            'instructions',
            'time_limit_minutes',
            'passing_score',
            'max_attempts',
            'available_from',
            'available_until',
            'show_correct_answers',
            'question_count',
            'total_points',
            'is_available',
            'course',
            'questions',
        )

    @extend_schema_field(ApiCourseReferenceSerializer)
    def get_course(self, obj):
        return ApiCourseReferenceSerializer(obj.course).data
