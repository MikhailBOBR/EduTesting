from django.contrib import admin

from .models import (
    Announcement,
    Answer,
    Attempt,
    AttemptAppeal,
    AttemptDraft,
    Choice,
    Course,
    Enrollment,
    Question,
    Quiz,
    QuizAccessOverride,
    UserNotification,
)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 1


class AnnouncementInline(admin.StackedInline):
    model = Announcement
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'order', 'topic', 'question_type', 'difficulty', 'points')
    list_filter = ('question_type', 'difficulty', 'quiz__course')
    search_fields = ('text', 'topic', 'quiz__title')
    inlines = [ChoiceInline]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject_code', 'semester', 'academic_year', 'owner', 'is_published')
    list_filter = ('is_published', 'semester', 'academic_year')
    search_fields = ('title', 'subject_code', 'summary', 'access_code', 'owner__username')
    inlines = [AnnouncementInline]


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'course',
        'time_limit_minutes',
        'passing_score',
        'submitted_attempts_count',
        'is_published',
    )
    list_filter = ('is_published', 'course')
    search_fields = ('title', 'course__title')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'is_important', 'published_at')
    list_filter = ('is_important', 'course')
    search_fields = ('title', 'body', 'course__title')


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('student__username', 'course__title')


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'quiz', 'status', 'score_percent', 'duration_seconds', 'submitted_at')
    list_filter = ('status', 'quiz__course')
    search_fields = ('student__username', 'quiz__title')


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'is_correct', 'awarded_points')
    list_filter = ('is_correct', 'question__quiz')


@admin.register(AttemptDraft)
class AttemptDraftAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'saved_at', 'autosave_count', 'answered_questions_count')
    search_fields = ('attempt__student__username', 'attempt__quiz__title')


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'category', 'title', 'is_read', 'created_at')
    list_filter = ('category', 'is_read')
    search_fields = ('recipient__username', 'title', 'message')


@admin.register(QuizAccessOverride)
class QuizAccessOverrideAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'student', 'extra_time_minutes', 'extra_attempts', 'is_active')
    list_filter = ('is_active', 'quiz__course')
    search_fields = ('quiz__title', 'student__username', 'student__last_name')


@admin.register(AttemptAppeal)
class AttemptAppealAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'student', 'status', 'resolved_at', 'resolved_by')
    list_filter = ('status', 'attempt__quiz__course')
    search_fields = ('student__username', 'attempt__quiz__title', 'message', 'teacher_response')
