import csv
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from accounts.mixins import StudentRequiredMixin, TeacherRequiredMixin

from .analytics import (
    build_attempt_comparison,
    build_attempt_integrity_flags,
    build_attempt_unlocked_achievements,
    build_attempt_topic_insights,
    build_course_attention_students,
    build_course_gradebook,
    build_course_integrity_overview,
    build_course_leaderboard,
    build_course_topic_diagnostics,
    build_student_achievements,
    build_student_topic_diagnostics,
)
from .forms import (
    AnnouncementForm,
    AttemptAppealForm,
    AttemptAppealReviewForm,
    AttemptForm,
    AttemptReviewForm,
    ChoiceForm,
    CourseFilterForm,
    CourseForm,
    JoinCourseForm,
    QuestionForm,
    QuizForm,
    QuizAccessOverrideForm,
)
from .models import (
    Announcement,
    AppealStatus,
    Attempt,
    AttemptAppeal,
    AttemptReview,
    AttemptStatus,
    Choice,
    Course,
    Enrollment,
    Question,
    Quiz,
    QuizAccessOverride,
    UserNotification,
)
from .services import (
    get_attempt_draft_mapping,
    notify_announcement,
    notify_attempt_appeal,
    notify_attempt_appeal_resolution,
    notify_attempt_review,
    notify_quiz,
    notify_quiz_override,
    save_attempt_draft,
    submit_attempt,
)


def build_student_progress(course, student):
    published_quizzes = course.quizzes.filter(is_published=True)
    total_quizzes = published_quizzes.count()
    submitted_attempts = Attempt.objects.filter(
        student=student,
        quiz__course=course,
        status=AttemptStatus.SUBMITTED,
    )
    completed_quizzes = submitted_attempts.values('quiz').distinct().count()
    average_score = submitted_attempts.aggregate(avg=Avg('score_percent'))['avg'] or 0
    completed_ids = submitted_attempts.values_list('quiz_id', flat=True)
    next_quiz = (
        published_quizzes.exclude(id__in=completed_ids)
        .order_by('available_until', 'title')
        .first()
    )

    return {
        'completed_quizzes': completed_quizzes,
        'total_quizzes': total_quizzes,
        'pending_quizzes': max(total_quizzes - completed_quizzes, 0),
        'progress_percent': round((completed_quizzes / total_quizzes) * 100) if total_quizzes else 0,
        'average_score': round(average_score),
        'next_quiz': next_quiz,
    }


def build_teacher_student_rows(course):
    rows = []
    total_quizzes = course.quizzes.filter(is_published=True).count()
    enrollments = course.enrollments.select_related('student').order_by(
        'student__last_name',
        'student__first_name',
        'student__username',
    )

    for enrollment in enrollments:
        attempts = Attempt.objects.filter(
            student=enrollment.student,
            quiz__course=course,
            status=AttemptStatus.SUBMITTED,
        )
        average_score = attempts.aggregate(avg=Avg('score_percent'))['avg'] or 0
        completed_quizzes = attempts.values('quiz').distinct().count()
        rows.append(
            {
                'enrollment': enrollment,
                'completed_quizzes': completed_quizzes,
                'total_quizzes': total_quizzes,
                'average_score': round(average_score),
            }
        )

    return rows


def enrich_attempt_with_integrity(attempt):
    flags = build_attempt_integrity_flags(attempt)
    attempt.integrity_flags_preview = flags
    attempt.integrity_flags_count = len(flags)
    attempt.integrity_risk_level = 'high' if any(flag['severity'] == 'high' for flag in flags) else ('medium' if flags else 'none')
    attempt.integrity_risk_label = 'Высокий риск' if attempt.integrity_risk_level == 'high' else ('Требует внимания' if flags else 'Без флагов')
    return attempt


def enrich_achievement(achievement):
    achievement = {
        **achievement,
        'level_label': {
            'bronze': 'Бронза',
            'silver': 'Серебро',
            'gold': 'Золото',
        }.get(achievement['level'], achievement['level']),
        'badge_class': {
            'bronze': 'badge-warning',
            'silver': '',
            'gold': 'badge-success',
        }.get(achievement['level'], ''),
    }
    return achievement


class HomeView(TemplateView):
    template_name = 'testing/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stats'] = {
            'courses': Course.objects.filter(is_published=True).count(),
            'quizzes': Quiz.objects.filter(is_published=True, course__is_published=True).count(),
            'students': Enrollment.objects.values('student').distinct().count(),
            'attempts': Attempt.objects.filter(status=AttemptStatus.SUBMITTED).count(),
            'announcements': Announcement.objects.filter(course__is_published=True).count(),
        }
        context['featured_courses'] = (
            Course.objects.filter(is_published=True)
            .select_related('owner')
            .order_by('title')[:6]
        )
        context['upcoming_quizzes'] = (
            Quiz.objects.filter(is_published=True, course__is_published=True)
            .select_related('course')
            .order_by('available_until', 'title')[:5]
        )
        context['recent_announcements'] = (
            Announcement.objects.filter(course__is_published=True)
            .select_related('course')
            .order_by('-is_important', '-published_at')[:5]
        )
        return context


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'testing/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        recent_notifications = (
            UserNotification.objects.filter(recipient=user)
            .select_related('course', 'quiz', 'attempt')
            .order_by('is_read', '-created_at')[:6]
        )
        unread_notifications_count = UserNotification.objects.filter(recipient=user, is_read=False).count()

        if user.is_teacher:
            managed_courses = Course.objects.filter(owner=user).order_by('title')
            pending_appeals = (
                AttemptAppeal.objects.filter(
                    attempt__quiz__course__owner=user,
                    status=AppealStatus.PENDING,
                )
                .select_related('attempt', 'attempt__quiz', 'attempt__student')
                .order_by('-created_at')[:6]
            )
            recent_attempts = list(
                Attempt.objects.filter(quiz__course__owner=user, status=AttemptStatus.SUBMITTED)
                .select_related('student', 'quiz', 'quiz__course')
                .order_by('-submitted_at')[:8]
            )
            recent_attempts = [enrich_attempt_with_integrity(attempt) for attempt in recent_attempts]
            average_score = (
                Attempt.objects.filter(quiz__course__owner=user, status=AttemptStatus.SUBMITTED)
                .aggregate(avg=Avg('score_percent'))['avg']
                or 0
            )
            distinct_students = (
                Enrollment.objects.filter(course__owner=user)
                .values('student')
                .distinct()
                .count()
            )
            course_overview = []
            suspicious_attempts = []
            flagged_attempts_total = 0
            for course in managed_courses:
                integrity = build_course_integrity_overview(course, limit=4)
                flagged_attempts_total += integrity['flagged_attempts_count']
                suspicious_attempts.extend(integrity['rows'])
            for course in managed_courses[:8]:
                next_deadline = (
                    course.quizzes.filter(is_published=True, available_until__isnull=False)
                    .order_by('available_until')
                    .first()
                )
                integrity = build_course_integrity_overview(course, limit=0)
                course_overview.append(
                    {
                        'course': course,
                        'students': course.total_students,
                        'quizzes': course.published_quizzes_count,
                        'average_score': course.average_score,
                        'completion_rate': course.completion_rate,
                        'next_deadline': next_deadline,
                        'flagged_attempts': integrity['flagged_attempts_count'],
                    }
                )
            suspicious_attempts.sort(
                key=lambda row: (
                    row['risk_score'],
                    row['attempt'].submitted_at or row['attempt'].created_at,
                ),
                reverse=True,
            )

            context.update(
                {
                    'summary': {
                        'courses': managed_courses.count(),
                        'students': distinct_students,
                        'attempts': Attempt.objects.filter(
                            quiz__course__owner=user,
                            status=AttemptStatus.SUBMITTED,
                        ).count(),
                        'average_score': round(average_score),
                        'unread_notifications': unread_notifications_count,
                        'flagged_attempts': flagged_attempts_total,
                        'pending_appeals': AttemptAppeal.objects.filter(
                            attempt__quiz__course__owner=user,
                            status=AppealStatus.PENDING,
                        ).count(),
                    },
                    'course_overview': course_overview,
                    'recent_attempts': recent_attempts,
                    'suspicious_attempts': suspicious_attempts[:6],
                    'pending_appeals': pending_appeals,
                    'recent_notifications': recent_notifications,
                    'recent_announcements': (
                        Announcement.objects.filter(course__owner=user)
                        .select_related('course')
                        .order_by('-is_important', '-published_at')[:6]
                    ),
                }
            )
        else:
            enrollments = Enrollment.objects.filter(student=user).select_related('course', 'course__owner')
            recent_attempts = list(
                Attempt.objects.filter(student=user, status=AttemptStatus.SUBMITTED)
                .select_related('quiz', 'quiz__course')
                .order_by('-submitted_at')[:8]
            )
            average_score = (
                Attempt.objects.filter(student=user, status=AttemptStatus.SUBMITTED)
                .aggregate(avg=Avg('score_percent'))['avg']
                or 0
            )
            open_appeals = (
                AttemptAppeal.objects.filter(student=user)
                .select_related('attempt', 'attempt__quiz')
                .order_by('status', '-created_at')[:6]
            )
            progress_rows = []
            pending_quizzes_total = 0
            achievements = [enrich_achievement(item) for item in build_student_achievements(user)]

            for enrollment in enrollments:
                progress = build_student_progress(enrollment.course, user)
                pending_quizzes_total += progress['pending_quizzes']
                progress_rows.append(
                    {
                        'course': enrollment.course,
                        'enrollment': enrollment,
                        **progress,
                        'latest_announcement': enrollment.course.announcements.first(),
                    }
                )

            context.update(
                {
                    'summary': {
                        'courses': enrollments.count(),
                        'completed_quizzes': Attempt.objects.filter(
                            student=user,
                            status=AttemptStatus.SUBMITTED,
                        )
                        .values('quiz')
                        .distinct()
                        .count(),
                        'average_score': round(average_score),
                        'pending_quizzes': pending_quizzes_total,
                        'unread_notifications': unread_notifications_count,
                        'achievements': len(achievements),
                        'open_appeals': AttemptAppeal.objects.filter(student=user, status=AppealStatus.PENDING).count(),
                    },
                    'course_progress': progress_rows,
                    'recent_attempts': recent_attempts,
                    'recent_achievements': achievements[:6],
                    'open_appeals': open_appeals,
                    'recent_notifications': recent_notifications,
                    'recent_announcements': (
                        Announcement.objects.filter(course__enrollments__student=user)
                        .select_related('course')
                        .distinct()
                        .order_by('-is_important', '-published_at')[:6]
                    ),
                    'join_form': JoinCourseForm(),
                }
            )

        return context


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = 'testing/notification_list.html'
    context_object_name = 'notifications'

    def get_queryset(self):
        return (
            UserNotification.objects.filter(recipient=self.request.user)
            .select_related('course', 'quiz', 'attempt')
            .order_by('is_read', '-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_count'] = UserNotification.objects.filter(
            recipient=self.request.user,
            is_read=False,
        ).count()
        return context


class NotificationMarkReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(UserNotification, pk=pk, recipient=request.user)
        notification.mark_as_read()
        return redirect(request.POST.get('next') or 'testing:notifications')


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    def post(self, request):
        unread_notifications = UserNotification.objects.filter(recipient=request.user, is_read=False)
        unread_notifications.update(is_read=True, read_at=timezone.now())
        return redirect(request.POST.get('next') or 'testing:notifications')


class CourseListView(ListView):
    template_name = 'testing/course_list.html'
    context_object_name = 'courses'

    def get_filter_form(self):
        return CourseFilterForm(self.request.GET or None)

    def get_queryset(self):
        queryset = Course.objects.select_related('owner')
        user = self.request.user
        if user.is_authenticated and user.is_teacher:
            queryset = queryset.filter(Q(is_published=True) | Q(owner=user)).distinct()
        else:
            queryset = queryset.filter(is_published=True)

        self.filter_form = self.get_filter_form()
        if self.filter_form.is_valid():
            query = self.filter_form.cleaned_data.get('q')
            semester = self.filter_form.cleaned_data.get('semester')

            if query:
                queryset = queryset.filter(
                    Q(title__icontains=query)
                    | Q(subject_code__icontains=query)
                    | Q(summary__icontains=query)
                    | Q(audience__icontains=query)
                )
            if semester:
                queryset = queryset.filter(semester=semester)

        return queryset.order_by('title')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = getattr(self, 'filter_form', self.get_filter_form())
        if self.request.user.is_authenticated and self.request.user.is_student:
            context['join_form'] = JoinCourseForm()
        return context


class CourseDetailView(DetailView):
    model = Course
    template_name = 'testing/course_detail.html'
    context_object_name = 'course'

    def get_queryset(self):
        queryset = Course.objects.select_related('owner')
        user = self.request.user
        if user.is_authenticated and user.is_teacher:
            return queryset.filter(Q(is_published=True) | Q(owner=user)).distinct()
        return queryset.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.object
        user = self.request.user
        can_manage = user.is_authenticated and user.is_teacher and course.owner_id == user.id
        quizzes = course.quizzes.order_by('created_at')

        if not can_manage:
            quizzes = quizzes.filter(is_published=True)

        quiz_rows = [
            {
                'quiz': quiz,
                'question_count': quiz.question_count,
                'total_points': quiz.total_points,
                'submitted_attempts_count': quiz.submitted_attempts_count,
                'average_score': quiz.average_score,
                'pass_rate': quiz.pass_rate,
            }
            for quiz in quizzes
        ]

        is_enrolled = (
            user.is_authenticated
            and user.is_student
            and Enrollment.objects.filter(course=course, student=user).exists()
        )

        context.update(
            {
                'can_manage': can_manage,
                'quiz_rows': quiz_rows,
                'students_count': course.total_students,
                'is_enrolled': is_enrolled,
                'announcements': course.announcements.all()[:8],
                'course_average_score': course.average_score,
                'course_completion_rate': course.completion_rate,
            }
        )

        if can_manage:
            context['student_rows'] = build_teacher_student_rows(course)
        elif is_enrolled:
            context['student_progress'] = build_student_progress(course, user)

        return context


class CourseInsightsView(LoginRequiredMixin, DetailView):
    model = Course
    template_name = 'testing/course_insights.html'
    context_object_name = 'course'

    def get_queryset(self):
        queryset = Course.objects.select_related('owner')
        user = self.request.user
        if user.is_authenticated and user.is_teacher:
            return queryset.filter(Q(is_published=True) | Q(owner=user)).distinct()
        return queryset.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.object
        user = self.request.user
        can_manage = user.is_authenticated and user.is_teacher and course.owner_id == user.id
        is_enrolled = (
            user.is_authenticated
            and user.is_student
            and Enrollment.objects.filter(course=course, student=user).exists()
        )

        if not can_manage and not is_enrolled:
            raise PermissionDenied

        context.update(
            {
                'can_manage': can_manage,
                'is_enrolled': is_enrolled,
            }
        )

        if can_manage:
            context['topic_diagnostics'] = build_course_topic_diagnostics(course)
            context['attention_students'] = build_course_attention_students(course)
            context['leaderboard'] = build_course_leaderboard(course)
            context['integrity_overview'] = build_course_integrity_overview(course)
        else:
            context['student_progress'] = build_student_progress(course, user)
            context['topic_diagnostics'] = build_student_topic_diagnostics(course, user)
            context['course_achievements'] = [enrich_achievement(item) for item in build_student_achievements(user, course=course)]

        return context


class CourseResultsExportView(TeacherRequiredMixin, View):
    def get(self, request, pk):
        course = get_object_or_404(Course.objects.select_related('owner'), pk=pk, owner=request.user)
        gradebook = build_course_gradebook(course)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="course_{course.pk}_results.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')

        header = [
            'Студент',
            'Логин',
            'Группа',
            'Статус записи',
            'Завершено тестов',
            'Осталось тестов',
            'Средний результат, %',
            'Лучший результат, %',
            'Последняя попытка',
        ]
        header.extend([f'{quiz.title} (%)' for quiz in gradebook['quizzes']])
        writer.writerow(header)

        for row in gradebook['rows']:
            last_submitted_at = (
                timezone.localtime(row['last_submitted_at']).strftime('%d.%m.%Y %H:%M')
                if row['last_submitted_at']
                else ''
            )
            writer.writerow(
                [
                    row['student'].get_full_name() or row['student'].username,
                    row['student'].username,
                    row['student'].academic_group or '',
                    row['enrollment'].get_status_display(),
                    row['completed_quizzes'],
                    row['pending_quizzes'],
                    row['average_score'],
                    row['best_score'],
                    last_submitted_at,
                    *[
                        row['quiz_scores'][quiz.id] if row['quiz_scores'][quiz.id] is not None else ''
                        for quiz in gradebook['quizzes']
                    ],
                ]
            )

        return response


class JoinCourseByCodeView(StudentRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = JoinCourseForm(request.POST)
        fallback_url = request.META.get('HTTP_REFERER') or reverse('testing:dashboard')

        if not form.is_valid():
            messages.error(request, 'Код курса заполнен некорректно.')
            return redirect(fallback_url)

        course = Course.objects.filter(
            access_code=form.cleaned_data['access_code'],
            is_published=True,
        ).first()
        if course is None:
            messages.error(request, 'Курс с таким кодом не найден или еще не опубликован.')
            return redirect(fallback_url)

        enrollment, created = Enrollment.objects.get_or_create(course=course, student=request.user)
        if created:
            messages.success(request, f'Вы успешно записаны на курс "{course.title}".')
        else:
            messages.info(request, 'Вы уже записаны на этот курс.')
        return redirect('testing:course_detail', pk=course.pk)


class EnrollInCourseView(StudentRequiredMixin, View):
    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk, is_published=True)
        enrollment, created = Enrollment.objects.get_or_create(course=course, student=request.user)
        if created:
            messages.success(request, 'Вы записались на курс. Материалы и тесты теперь доступны в личном кабинете.')
        else:
            messages.info(request, 'Вы уже записаны на этот курс.')
        return redirect('testing:course_detail', pk=course.pk)


class CourseCreateView(TeacherRequiredMixin, CreateView):
    form_class = CourseForm
    template_name = 'testing/course_form.html'

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Курс создан.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Создание курса'
        return context

    def get_success_url(self):
        return reverse('testing:course_detail', kwargs={'pk': self.object.pk})


class CourseUpdateView(TeacherRequiredMixin, UpdateView):
    form_class = CourseForm
    model = Course
    template_name = 'testing/course_form.html'

    def get_queryset(self):
        return Course.objects.filter(owner=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Изменения по курсу сохранены.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Редактирование курса'
        return context

    def get_success_url(self):
        return reverse('testing:course_detail', kwargs={'pk': self.object.pk})


class AnnouncementCreateView(TeacherRequiredMixin, CreateView):
    form_class = AnnouncementForm
    template_name = 'testing/announcement_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.course = get_object_or_404(Course, pk=kwargs['course_pk'], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        response = super().form_valid(form)
        notify_announcement(self.object)
        messages.success(self.request, 'Объявление опубликовано.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Новое объявление для курса "{self.course.title}"'
        context['course'] = self.course
        return context

    def get_success_url(self):
        return reverse('testing:course_detail', kwargs={'pk': self.course.pk})


class AnnouncementUpdateView(TeacherRequiredMixin, UpdateView):
    form_class = AnnouncementForm
    model = Announcement
    template_name = 'testing/announcement_form.html'

    def get_queryset(self):
        return Announcement.objects.filter(course__owner=self.request.user).select_related('course')

    def form_valid(self, form):
        messages.success(self.request, 'Объявление обновлено.')
        changed_data = set(form.changed_data)
        response = super().form_valid(form)
        if changed_data:
            notify_announcement(self.object, updated=True)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Редактирование объявления'
        context['course'] = self.object.course
        return context

    def get_success_url(self):
        return reverse('testing:course_detail', kwargs={'pk': self.object.course.pk})


class QuizCreateView(TeacherRequiredMixin, CreateView):
    form_class = QuizForm
    template_name = 'testing/quiz_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.course = get_object_or_404(Course, pk=kwargs['course_pk'], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        response = super().form_valid(form)
        if self.object.is_published:
            notify_quiz(self.object)
        messages.success(self.request, 'Тест создан.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Новый тест для курса "{self.course.title}"'
        context['course'] = self.course
        return context

    def get_success_url(self):
        return reverse('testing:quiz_detail', kwargs={'pk': self.object.pk})


class QuizUpdateView(TeacherRequiredMixin, UpdateView):
    form_class = QuizForm
    model = Quiz
    template_name = 'testing/quiz_form.html'

    def get_queryset(self):
        return Quiz.objects.filter(course__owner=self.request.user).select_related('course')

    def form_valid(self, form):
        messages.success(self.request, 'Параметры теста обновлены.')
        previous_quiz = self.get_queryset().get(pk=self.object.pk)
        changed_data = set(form.changed_data)
        response = super().form_valid(form)
        should_notify = self.object.is_published and (
            not previous_quiz.is_published
            or bool(changed_data & {'title', 'description', 'available_from', 'available_until', 'time_limit_minutes'})
        )
        if should_notify:
            notify_quiz(self.object, updated=previous_quiz.is_published)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Редактирование теста "{self.object.title}"'
        context['course'] = self.object.course
        return context

    def get_success_url(self):
        return reverse('testing:quiz_detail', kwargs={'pk': self.object.pk})


class QuizAccessOverrideListView(TeacherRequiredMixin, ListView):
    template_name = 'testing/quiz_override_list.html'
    context_object_name = 'overrides'

    def dispatch(self, request, *args, **kwargs):
        self.quiz = get_object_or_404(
            Quiz.objects.select_related('course'),
            pk=kwargs['pk'],
            course__owner=request.user,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            QuizAccessOverride.objects.filter(quiz=self.quiz)
            .select_related('student')
            .order_by('-is_active', 'student__last_name', 'student__first_name', 'student__username')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['quiz'] = self.quiz
        context['active_overrides_count'] = self.quiz.access_overrides.filter(is_active=True).count()
        return context


class QuizAccessOverrideCreateView(TeacherRequiredMixin, CreateView):
    form_class = QuizAccessOverrideForm
    template_name = 'testing/quiz_override_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.quiz = get_object_or_404(
            Quiz.objects.select_related('course'),
            pk=kwargs['pk'],
            course__owner=request.user,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['quiz'] = self.quiz
        return kwargs

    def form_valid(self, form):
        form.instance.quiz = self.quiz
        response = super().form_valid(form)
        notify_quiz_override(self.object)
        messages.success(self.request, 'Индивидуальные условия сохранены.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['quiz'] = self.quiz
        context['page_title'] = f'Новые индивидуальные условия для теста "{self.quiz.title}"'
        return context

    def get_success_url(self):
        return reverse('testing:quiz_overrides', kwargs={'pk': self.quiz.pk})


class QuizAccessOverrideUpdateView(TeacherRequiredMixin, UpdateView):
    form_class = QuizAccessOverrideForm
    model = QuizAccessOverride
    template_name = 'testing/quiz_override_form.html'

    def get_queryset(self):
        return QuizAccessOverride.objects.filter(quiz__course__owner=self.request.user).select_related('quiz', 'student')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['quiz'] = self.object.quiz
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Индивидуальные условия обновлены.')
        response = super().form_valid(form)
        notify_quiz_override(self.object, updated=True)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['quiz'] = self.object.quiz
        context['page_title'] = f'Редактирование индивидуальных условий для "{self.object.student.get_full_name() or self.object.student.username}"'
        return context

    def get_success_url(self):
        return reverse('testing:quiz_overrides', kwargs={'pk': self.object.quiz.pk})


class QuestionCreateView(TeacherRequiredMixin, CreateView):
    form_class = QuestionForm
    template_name = 'testing/question_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.quiz = get_object_or_404(Quiz, pk=kwargs['quiz_pk'], course__owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.quiz = self.quiz
        response = super().form_valid(form)
        messages.success(self.request, 'Вопрос добавлен.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Новый вопрос для теста "{self.quiz.title}"'
        context['quiz'] = self.quiz
        return context

    def get_success_url(self):
        return reverse('testing:quiz_detail', kwargs={'pk': self.quiz.pk})


class QuestionUpdateView(TeacherRequiredMixin, UpdateView):
    form_class = QuestionForm
    model = Question
    template_name = 'testing/question_form.html'

    def get_queryset(self):
        return Question.objects.filter(quiz__course__owner=self.request.user).select_related('quiz')

    def form_valid(self, form):
        messages.success(self.request, 'Вопрос обновлен.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Редактирование вопроса #{self.object.order}'
        context['quiz'] = self.object.quiz
        return context

    def get_success_url(self):
        return reverse('testing:quiz_detail', kwargs={'pk': self.object.quiz.pk})


class ChoiceCreateView(TeacherRequiredMixin, CreateView):
    form_class = ChoiceForm
    template_name = 'testing/choice_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.question = get_object_or_404(
            Question.objects.select_related('quiz'),
            pk=kwargs['question_pk'],
            quiz__course__owner=request.user,
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.question = self.question
        response = super().form_valid(form)
        messages.success(self.request, 'Вариант ответа добавлен.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Новый вариант ответа для вопроса #{self.question.order}'
        context['question'] = self.question
        return context

    def get_success_url(self):
        return reverse('testing:quiz_detail', kwargs={'pk': self.question.quiz.pk})


class ChoiceUpdateView(TeacherRequiredMixin, UpdateView):
    form_class = ChoiceForm
    template_name = 'testing/choice_form.html'
    model = Choice

    def get_queryset(self):
        return Choice.objects.filter(question__quiz__course__owner=self.request.user).select_related(
            'question',
            'question__quiz',
        )

    def form_valid(self, form):
        messages.success(self.request, 'Вариант ответа обновлен.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Редактирование варианта ответа'
        context['question'] = self.object.question
        return context

    def get_success_url(self):
        return reverse('testing:quiz_detail', kwargs={'pk': self.object.question.quiz.pk})


class QuizDetailView(DetailView):
    model = Quiz
    template_name = 'testing/quiz_detail.html'
    context_object_name = 'quiz'

    def get_queryset(self):
        queryset = Quiz.objects.select_related('course', 'course__owner').prefetch_related('questions__choices')
        user = self.request.user
        if user.is_authenticated and user.is_teacher:
            return queryset.filter(Q(is_published=True, course__is_published=True) | Q(course__owner=user)).distinct()
        return queryset.filter(is_published=True, course__is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        quiz = self.object
        user = self.request.user
        can_manage = user.is_authenticated and user.is_teacher and quiz.course.owner_id == user.id
        is_enrolled = (
            user.is_authenticated
            and user.is_student
            and Enrollment.objects.filter(course=quiz.course, student=user).exists()
        )
        submitted_attempts = []
        in_progress_attempt = None
        personal_override = None
        effective_time_limit_minutes = quiz.time_limit_minutes
        effective_max_attempts = quiz.max_attempts

        if user.is_authenticated and user.is_student:
            submitted_attempts = Attempt.objects.filter(
                quiz=quiz,
                student=user,
                status=AttemptStatus.SUBMITTED,
            ).order_by('-submitted_at')
            in_progress_attempt = Attempt.objects.filter(
                quiz=quiz,
                student=user,
                status=AttemptStatus.IN_PROGRESS,
            ).first()
            if is_enrolled:
                personal_override = quiz.get_access_override(user)
                effective_time_limit_minutes = quiz.get_effective_time_limit(user)
                effective_max_attempts = quiz.get_effective_max_attempts(user)

        context.update(
            {
                'can_manage': can_manage,
                'is_enrolled': is_enrolled,
                'remaining_attempts': quiz.remaining_attempts(user) if is_enrolled else 0,
                'submitted_attempts': submitted_attempts,
                'in_progress_attempt': in_progress_attempt,
                'personal_override': personal_override,
                'effective_time_limit_minutes': effective_time_limit_minutes,
                'effective_max_attempts': effective_max_attempts,
                'can_start': is_enrolled and quiz.is_available and (
                    quiz.remaining_attempts(user) > 0 or in_progress_attempt is not None
                ),
                'quiz_metrics': {
                    'question_count': quiz.question_count,
                    'total_points': quiz.total_points,
                    'submitted_attempts': quiz.submitted_attempts_count,
                    'average_score': quiz.average_score,
                    'pass_rate': quiz.pass_rate,
                    'unconfigured_questions': quiz.unanswered_configuration_count,
                    'active_overrides': quiz.access_overrides.filter(is_active=True).count(),
                },
            }
        )

        if can_manage:
            context['recent_attempts'] = (
                Attempt.objects.filter(quiz=quiz, status=AttemptStatus.SUBMITTED)
                .select_related('student')
                .order_by('-submitted_at')[:6]
            )
        return context


class StartAttemptView(StudentRequiredMixin, View):
    def post(self, request, pk):
        quiz = get_object_or_404(
            Quiz.objects.select_related('course'),
            pk=pk,
            is_published=True,
            course__is_published=True,
        )

        if not Enrollment.objects.filter(course=quiz.course, student=request.user).exists():
            messages.error(request, 'Сначала запишитесь на курс, чтобы пройти тест.')
            return redirect('testing:course_detail', pk=quiz.course.pk)

        if not quiz.is_available:
            messages.error(request, 'Тест пока недоступен для прохождения.')
            return redirect('testing:quiz_detail', pk=quiz.pk)

        if not quiz.questions.exists():
            messages.error(request, 'Преподаватель еще не добавил вопросы в этот тест.')
            return redirect('testing:quiz_detail', pk=quiz.pk)

        if quiz.unanswered_configuration_count:
            messages.error(request, 'Тест еще не полностью настроен преподавателем.')
            return redirect('testing:quiz_detail', pk=quiz.pk)

        attempt = Attempt.objects.filter(
            quiz=quiz,
            student=request.user,
            status=AttemptStatus.IN_PROGRESS,
        ).first()

        if attempt is None:
            if quiz.remaining_attempts(request.user) <= 0:
                messages.error(request, 'Лимит попыток исчерпан.')
                return redirect('testing:quiz_detail', pk=quiz.pk)

            attempt = Attempt.objects.create(
                quiz=quiz,
                student=request.user,
                time_limit_minutes_snapshot=quiz.get_effective_time_limit(request.user),
            )

        messages.info(request, 'Попытка активна. Ответьте на вопросы и отправьте работу на проверку.')
        return redirect('testing:attempt_detail', pk=attempt.pk)


class AttemptDetailView(LoginRequiredMixin, View):
    template_name = 'testing/attempt_form.html'

    def get_attempt(self):
        attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student').prefetch_related(
                'quiz__questions__choices'
            ),
            pk=self.kwargs['pk'],
        )
        if attempt.student_id != self.request.user.id:
            raise PermissionDenied
        return attempt

    def get_context_payload(self, attempt, form):
        draft = getattr(attempt, 'draft', None)
        return {
            'attempt': attempt,
            'quiz': attempt.quiz,
            'form': form,
            'deadline_at': attempt.deadline_at,
            'draft': draft,
            'effective_time_limit_minutes': attempt.effective_time_limit_minutes,
            'has_personal_time_limit': attempt.effective_time_limit_minutes != attempt.quiz.time_limit_minutes,
        }

    def get(self, request, *args, **kwargs):
        attempt = self.get_attempt()
        if attempt.status == AttemptStatus.SUBMITTED:
            return redirect('testing:attempt_result', pk=attempt.pk)

        form = AttemptForm(quiz=attempt.quiz, initial_answers=get_attempt_draft_mapping(attempt))
        return render(request, self.template_name, self.get_context_payload(attempt, form))

    def post(self, request, *args, **kwargs):
        attempt = self.get_attempt()
        if attempt.status == AttemptStatus.SUBMITTED:
            return redirect('testing:attempt_result', pk=attempt.pk)

        form = AttemptForm(request.POST, quiz=attempt.quiz)
        if form.is_valid():
            submit_attempt(attempt, form.get_answers_mapping())
            messages.success(request, 'Тест завершен, результат сохранен.')
            return redirect('testing:attempt_result', pk=attempt.pk)

        return render(request, self.template_name, self.get_context_payload(attempt, form))


class AttemptDraftSaveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student').prefetch_related('quiz__questions__choices'),
            pk=pk,
            student=request.user,
        )
        if attempt.status == AttemptStatus.SUBMITTED:
            return JsonResponse({'detail': 'Draft is not available for a submitted attempt.'}, status=400)

        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON payload.'}, status=400)

        draft = save_attempt_draft(
            attempt,
            payload.get('answers', {}),
            last_question_id=payload.get('last_question_id'),
        )
        return JsonResponse(
            {
                'saved_at': timezone.localtime(draft.saved_at).strftime('%d.%m.%Y %H:%M:%S'),
                'answered_questions_count': draft.answered_questions_count,
                'autosave_count': draft.autosave_count,
                'last_question_id': draft.last_question_id,
            }
        )


class AttemptResultView(LoginRequiredMixin, DetailView):
    model = Attempt
    template_name = 'testing/attempt_result.html'
    context_object_name = 'attempt'

    def get_object(self, queryset=None):
        attempt = super().get_object(queryset)
        user = self.request.user
        if attempt.student_id == user.id:
            return attempt
        if user.is_teacher and attempt.quiz.course.owner_id == user.id:
            return attempt
        raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        show_answer_key = self.request.user.is_teacher or self.object.quiz.show_correct_answers
        context['answers'] = (
            self.object.answers.select_related('question')
            .prefetch_related('selected_choices', 'question__choices')
            .all()
        )
        context['show_answer_key'] = show_answer_key
        context['can_review'] = self.request.user.is_teacher and self.object.quiz.course.owner_id == self.request.user.id
        context['attempt_review'] = getattr(self.object, 'review', None)
        context['attempt_appeal'] = getattr(self.object, 'appeal', None)
        context['can_appeal'] = self.request.user.is_student and self.object.student_id == self.request.user.id
        context['can_manage_appeal'] = (
            self.request.user.is_teacher
            and self.object.quiz.course.owner_id == self.request.user.id
            and hasattr(self.object, 'appeal')
        )
        context['topic_insights'] = build_attempt_topic_insights(self.object)
        context['attempt_comparison'] = build_attempt_comparison(self.object)
        context['integrity_flags'] = build_attempt_integrity_flags(self.object) if self.request.user.is_teacher else []
        context['unlocked_achievements'] = [
            enrich_achievement(item) for item in build_attempt_unlocked_achievements(self.object)
        ]
        return context


class AttemptReviewView(TeacherRequiredMixin, UpdateView):
    form_class = AttemptReviewForm
    model = AttemptReview
    template_name = 'testing/attempt_review_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student'),
            pk=kwargs['pk'],
            quiz__course__owner=request.user,
            status=AttemptStatus.SUBMITTED,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return AttemptReview.objects.filter(attempt=self.attempt).first()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if kwargs.get('instance') is None:
            kwargs['instance'] = AttemptReview(attempt=self.attempt, teacher=self.request.user)
        return kwargs

    def form_valid(self, form):
        form.instance.attempt = self.attempt
        form.instance.teacher = self.request.user
        form.instance.reviewed_at = timezone.now()
        messages.success(self.request, 'Комментарий преподавателя сохранен.')
        updated = self.get_object() is not None
        response = super().form_valid(form)
        notify_attempt_review(self.object, updated=updated)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attempt'] = self.attempt
        context['page_title'] = 'Комментарий к попытке'
        return context

    def get_success_url(self):
        return reverse('testing:attempt_result', kwargs={'pk': self.attempt.pk})


class AttemptAppealEditView(StudentRequiredMixin, UpdateView):
    form_class = AttemptAppealForm
    model = AttemptAppeal
    template_name = 'testing/attempt_appeal_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            Attempt.objects.select_related('quiz', 'quiz__course', 'student'),
            pk=kwargs['pk'],
            student=request.user,
            status=AttemptStatus.SUBMITTED,
        )
        existing_appeal = AttemptAppeal.objects.filter(attempt=self.attempt).first()
        if existing_appeal and existing_appeal.status != AppealStatus.PENDING:
            messages.info(request, 'Апелляция уже рассмотрена преподавателем и больше не редактируется.')
            return redirect('testing:attempt_result', pk=self.attempt.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return AttemptAppeal.objects.filter(attempt=self.attempt).first()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if kwargs.get('instance') is None:
            kwargs['instance'] = AttemptAppeal(attempt=self.attempt, student=self.request.user)
        return kwargs

    def form_valid(self, form):
        existing_appeal = self.get_object()
        form.instance.attempt = self.attempt
        form.instance.student = self.request.user
        form.instance.status = AppealStatus.PENDING
        form.instance.teacher_response = ''
        form.instance.resolved_by = None
        form.instance.resolved_at = None
        response = super().form_valid(form)
        notify_attempt_appeal(self.object, updated=existing_appeal is not None)
        messages.success(self.request, 'Апелляция сохранена и отправлена преподавателю.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attempt'] = self.attempt
        context['page_title'] = 'Апелляция по попытке'
        return context

    def get_success_url(self):
        return reverse('testing:attempt_result', kwargs={'pk': self.attempt.pk})


class AttemptAppealReviewView(TeacherRequiredMixin, UpdateView):
    form_class = AttemptAppealReviewForm
    model = AttemptAppeal
    template_name = 'testing/attempt_appeal_review_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.appeal = get_object_or_404(
            AttemptAppeal.objects.select_related('attempt', 'attempt__quiz', 'attempt__quiz__course', 'student'),
            attempt_id=kwargs['pk'],
            attempt__quiz__course__owner=request.user,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.appeal

    def form_valid(self, form):
        form.instance.resolved_by = None
        form.instance.resolved_at = None
        if form.cleaned_data['status'] != AppealStatus.PENDING:
            form.instance.resolved_by = self.request.user
            form.instance.resolved_at = timezone.now()
        response = super().form_valid(form)
        if self.object.status != AppealStatus.PENDING:
            notify_attempt_appeal_resolution(self.object)
        messages.success(self.request, 'Решение по апелляции сохранено.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attempt'] = self.appeal.attempt
        context['appeal'] = self.appeal
        context['page_title'] = 'Рассмотрение апелляции'
        return context

    def get_success_url(self):
        return reverse('testing:attempt_result', kwargs={'pk': self.appeal.attempt_id})


class QuizAttemptsView(TeacherRequiredMixin, ListView):
    template_name = 'testing/quiz_attempts.html'
    context_object_name = 'attempts'

    def dispatch(self, request, *args, **kwargs):
        self.quiz = get_object_or_404(
            Quiz.objects.select_related('course'),
            pk=kwargs['pk'],
            course__owner=request.user,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        attempts = list(
            Attempt.objects.filter(quiz=self.quiz, status=AttemptStatus.SUBMITTED)
            .select_related('student', 'review')
            .order_by('-submitted_at')
        )
        return [enrich_attempt_with_integrity(attempt) for attempt in attempts]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        integrity_rows = [attempt for attempt in context['attempts'] if attempt.integrity_flags_count]
        context['quiz'] = self.quiz
        context['analytics'] = {
            'attempts': self.quiz.submitted_attempts_count,
            'average_score': self.quiz.average_score,
            'pass_rate': self.quiz.pass_rate,
            'reviewed_attempts': AttemptReview.objects.filter(attempt__quiz=self.quiz).count(),
            'flagged_attempts': len(integrity_rows),
        }
        return context
