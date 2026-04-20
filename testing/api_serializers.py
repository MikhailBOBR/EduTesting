from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Announcement, Attempt, AttemptReview, Choice, Course, Question, Quiz


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


class ApiUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    academic_group = serializers.CharField(read_only=True)


class ApiTokenRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class ApiTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = ApiUserSerializer()


class ApiCourseReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ('id', 'title', 'subject_code')


class ApiQuizReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quiz
        fields = ('id', 'title')


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


class ApiMyCourseSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    total_students = serializers.IntegerField(read_only=True)
    published_quizzes_count = serializers.IntegerField(read_only=True)
    my_role = serializers.SerializerMethodField()
    enrollment_status = serializers.SerializerMethodField()

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
            'total_students',
            'my_role',
            'enrollment_status',
        )

    @extend_schema_field(serializers.CharField())
    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.username

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_enrollment_status(self, obj):
        user = self.context['request'].user
        if not user.is_student:
            return None
        enrollment = obj.enrollments.filter(student=user).first()
        return enrollment.status if enrollment else None

    @extend_schema_field(serializers.CharField())
    def get_my_role(self, obj):
        return self.context['request'].user.role


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


class ApiEnrollmentResponseSerializer(serializers.Serializer):
    course = ApiCourseReferenceSerializer()
    enrolled = serializers.BooleanField()
    status = serializers.CharField()


class ApiAttemptReviewSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = AttemptReview
        fields = ('feedback', 'reviewed_at', 'teacher_name')

    @extend_schema_field(serializers.CharField())
    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.username


class ApiAttemptSummarySerializer(serializers.ModelSerializer):
    quiz = ApiQuizReferenceSerializer(read_only=True)
    course = serializers.SerializerMethodField()
    is_passed = serializers.BooleanField(read_only=True)
    total_questions = serializers.IntegerField(read_only=True)
    total_points = serializers.IntegerField(read_only=True)
    has_review = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = (
            'id',
            'status',
            'started_at',
            'submitted_at',
            'duration_seconds',
            'score_points',
            'score_percent',
            'correct_answers_count',
            'total_questions',
            'total_points',
            'is_passed',
            'quiz',
            'course',
            'has_review',
        )

    @extend_schema_field(ApiCourseReferenceSerializer)
    def get_course(self, obj):
        return ApiCourseReferenceSerializer(obj.quiz.course).data

    @extend_schema_field(serializers.BooleanField())
    def get_has_review(self, obj):
        return hasattr(obj, 'review')


class ApiAttemptAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    question_text = serializers.CharField()
    topic = serializers.CharField()
    is_correct = serializers.BooleanField()
    awarded_points = serializers.IntegerField()
    selected_choice_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)
    selected_choices = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    correct_choice_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)
    correct_choices = serializers.ListField(child=serializers.CharField(), allow_empty=True)


class ApiTopicInsightSerializer(serializers.Serializer):
    topic = serializers.CharField()
    accuracy_percent = serializers.IntegerField()
    awarded_points = serializers.IntegerField()
    total_points = serializers.IntegerField()
    status_code = serializers.CharField()
    status_label = serializers.CharField()
    recommendation = serializers.CharField()


class ApiAttemptComparisonTopicSerializer(serializers.Serializer):
    topic = serializers.CharField()
    previous_accuracy = serializers.IntegerField()
    current_accuracy = serializers.IntegerField()
    delta_accuracy = serializers.IntegerField()
    trend = serializers.CharField()


class ApiAttemptComparisonSerializer(serializers.Serializer):
    previous_attempt_id = serializers.IntegerField()
    previous_submitted_at = serializers.DateTimeField()
    previous_score_percent = serializers.IntegerField()
    score_delta = serializers.IntegerField()
    points_delta = serializers.IntegerField()
    correct_answers_delta = serializers.IntegerField()
    duration_delta_minutes = serializers.FloatField()
    improved_topics = ApiAttemptComparisonTopicSerializer(many=True)
    declined_topics = ApiAttemptComparisonTopicSerializer(many=True)
    unchanged_topics_count = serializers.IntegerField()


class ApiAttemptDetailSerializer(serializers.Serializer):
    attempt = ApiAttemptSummarySerializer()
    answers = ApiAttemptAnswerSerializer(many=True)
    topic_insights = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    recommendations = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    review = ApiAttemptReviewSerializer(allow_null=True)
    show_answer_key = serializers.BooleanField()
    comparison = ApiAttemptComparisonSerializer(allow_null=True)


class ApiAttemptStartResponseSerializer(serializers.Serializer):
    attempt = ApiAttemptSummarySerializer()
    reused_existing = serializers.BooleanField()


class ApiAttemptSubmitRequestSerializer(serializers.Serializer):
    answers = serializers.DictField(
        child=serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True)
    )

    def validate_answers(self, value):
        normalized = {}
        for question_id, choice_ids in value.items():
            try:
                normalized[int(question_id)] = {int(choice_id) for choice_id in choice_ids}
            except (TypeError, ValueError):
                raise serializers.ValidationError('Ключи словаря answers должны быть числовыми id вопросов.')
        return normalized


class ApiAttemptDraftSerializer(serializers.Serializer):
    saved_at = serializers.DateTimeField()
    autosave_count = serializers.IntegerField()
    answered_questions_count = serializers.IntegerField()
    last_question_id = serializers.IntegerField(allow_null=True)


class ApiAttemptDraftSaveRequestSerializer(ApiAttemptSubmitRequestSerializer):
    last_question_id = serializers.IntegerField(required=False, allow_null=True)


class ApiQuizAttemptListSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    academic_group = serializers.CharField(source='student.academic_group', read_only=True)
    has_review = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = (
            'id',
            'student_name',
            'academic_group',
            'submitted_at',
            'duration_seconds',
            'score_points',
            'score_percent',
            'has_review',
        )

    @extend_schema_field(serializers.CharField())
    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    @extend_schema_field(serializers.BooleanField())
    def get_has_review(self, obj):
        return hasattr(obj, 'review')


class ApiQuizAttemptsResponseSerializer(serializers.Serializer):
    quiz = ApiQuizReferenceSerializer()
    attempts = ApiQuizAttemptListSerializer(many=True)


class ApiAnalyticsTopicRowSerializer(serializers.Serializer):
    topic = serializers.CharField()
    total_questions = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    awarded_points = serializers.IntegerField()
    total_points = serializers.IntegerField()
    accuracy_percent = serializers.IntegerField()
    points_percent = serializers.IntegerField()
    status_code = serializers.CharField()
    status_label = serializers.CharField()
    recommendation = serializers.CharField()
    students_count = serializers.IntegerField(required=False)
    attempts_count = serializers.IntegerField(required=False)


class ApiAttentionStudentSerializer(serializers.Serializer):
    student = ApiUserSerializer()
    completed_quizzes = serializers.IntegerField()
    pending_quizzes = serializers.IntegerField()
    average_score = serializers.IntegerField()
    weakest_topic = serializers.CharField(allow_null=True)
    status_code = serializers.CharField()
    status_label = serializers.CharField()
    recommendation = serializers.CharField()


class ApiLeaderboardRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    student = ApiUserSerializer()
    average_score = serializers.IntegerField()
    best_score = serializers.IntegerField()
    completed_quizzes = serializers.IntegerField()
    pending_quizzes = serializers.IntegerField()
    progress_percent = serializers.IntegerField()
    status_code = serializers.CharField()
    status_label = serializers.CharField()


class ApiCourseAnalyticsSerializer(serializers.Serializer):
    course = ApiCourseReferenceSerializer()
    overall_accuracy = serializers.IntegerField()
    weak_topics_count = serializers.IntegerField()
    total_answers = serializers.IntegerField()
    topic_rows = ApiAnalyticsTopicRowSerializer(many=True)
    attention_students = ApiAttentionStudentSerializer(many=True)
    leaderboard = ApiLeaderboardRowSerializer(many=True)
