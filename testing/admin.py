from django.contrib import admin

from .models import (
    Announcement,
    Answer,
    Attempt,
    AttemptAppeal,
    AttemptDraft,
    AttemptReview,
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


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ('question', 'order', 'text', 'is_correct')
    list_filter = ('is_correct', 'question__quiz')
    search_fields = ('text', 'question__text', 'question__quiz__title')
    autocomplete_fields = ('question',)


@admin.action(description='Опубликовать выбранные курсы')
def publish_courses(modeladmin, request, queryset):
    queryset.update(is_published=True)


@admin.action(description='Снять с публикации выбранные курсы')
def unpublish_courses(modeladmin, request, queryset):
    queryset.update(is_published=False)


@admin.action(description='Опубликовать выбранные тесты')
def publish_quizzes(modeladmin, request, queryset):
    queryset.update(is_published=True)


@admin.action(description='Снять с публикации выбранные тесты')
def unpublish_quizzes(modeladmin, request, queryset):
    queryset.update(is_published=False)


@admin.action(description='Отметить уведомления как прочитанные')
def mark_notifications_read(modeladmin, request, queryset):
    queryset.update(is_read=True)


@admin.action(description='Отметить уведомления как непрочитанные')
def mark_notifications_unread(modeladmin, request, queryset):
    queryset.update(is_read=False)


@admin.action(description='Активировать выбранные индивидуальные условия')
def activate_overrides(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description='Отключить выбранные индивидуальные условия')
def deactivate_overrides(modeladmin, request, queryset):
    queryset.update(is_active=False)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'order', 'topic', 'question_type', 'difficulty', 'points')
    list_filter = ('question_type', 'difficulty', 'quiz__course')
    search_fields = ('text', 'topic', 'quiz__title')
    autocomplete_fields = ('quiz',)
    inlines = [ChoiceInline]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject_code', 'semester', 'academic_year', 'owner', 'is_published')
    list_filter = ('is_published', 'semester', 'academic_year')
    search_fields = ('title', 'subject_code', 'summary', 'access_code', 'owner__username')
    autocomplete_fields = ('owner',)
    actions = (publish_courses, unpublish_courses)
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
    autocomplete_fields = ('course',)
    actions = (publish_quizzes, unpublish_quizzes)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'is_important', 'published_at')
    list_filter = ('is_important', 'course')
    search_fields = ('title', 'body', 'course__title')
    autocomplete_fields = ('course',)
    readonly_fields = ('published_at',)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('student__username', 'course__title')
    autocomplete_fields = ('student', 'course')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'quiz',
        'status',
        'score_percent',
        'duration_seconds',
        'time_limit_minutes_snapshot',
        'submitted_at',
    )
    list_filter = ('status', 'quiz__course')
    search_fields = ('student__username', 'quiz__title')
    autocomplete_fields = ('student', 'quiz')
    readonly_fields = ('started_at', 'submitted_at', 'duration_seconds')


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'is_correct', 'awarded_points')
    list_filter = ('is_correct', 'question__quiz')
    autocomplete_fields = ('attempt', 'question', 'selected_choices')


@admin.register(AttemptDraft)
class AttemptDraftAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'saved_at', 'autosave_count', 'answered_questions_count')
    search_fields = ('attempt__student__username', 'attempt__quiz__title')
    autocomplete_fields = ('attempt',)
    readonly_fields = ('saved_at', 'autosave_count', 'answered_questions_count')


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'category', 'title', 'is_read', 'created_at')
    list_filter = ('category', 'is_read')
    search_fields = ('recipient__username', 'title', 'message')
    autocomplete_fields = ('recipient', 'attempt')
    readonly_fields = ('created_at',)
    actions = (mark_notifications_read, mark_notifications_unread)


@admin.register(QuizAccessOverride)
class QuizAccessOverrideAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'student', 'extra_time_minutes', 'extra_attempts', 'is_active')
    list_filter = ('is_active', 'quiz__course')
    search_fields = ('quiz__title', 'student__username', 'student__last_name')
    autocomplete_fields = ('quiz', 'student')
    readonly_fields = ('created_at', 'updated_at')
    actions = (activate_overrides, deactivate_overrides)


@admin.register(AttemptAppeal)
class AttemptAppealAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'student', 'status', 'resolved_at', 'resolved_by')
    list_filter = ('status', 'attempt__quiz__course')
    search_fields = ('student__username', 'attempt__quiz__title', 'message', 'teacher_response')
    autocomplete_fields = ('attempt', 'student', 'resolved_by')
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')


@admin.register(AttemptReview)
class AttemptReviewAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'teacher', 'reviewed_at')
    search_fields = ('attempt__quiz__title', 'attempt__student__username', 'teacher__username', 'feedback')
    autocomplete_fields = ('attempt', 'teacher')
    readonly_fields = ('reviewed_at',)
