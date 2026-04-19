from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from accounts.mixins import StudentRequiredMixin, TeacherRequiredMixin

from .analytics import (
    build_attempt_topic_insights,
    build_course_attention_students,
    build_course_topic_diagnostics,
    build_student_topic_diagnostics,
)
from .forms import (
    AnnouncementForm,
    AttemptForm,
    ChoiceForm,
    CourseFilterForm,
    CourseForm,
    JoinCourseForm,
    QuestionForm,
    QuizForm,
)
from .models import Announcement, Attempt, AttemptStatus, Choice, Course, Enrollment, Question, Quiz
from .services import submit_attempt


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

        if user.is_teacher:
            managed_courses = Course.objects.filter(owner=user).order_by('title')
            recent_attempts = (
                Attempt.objects.filter(quiz__course__owner=user, status=AttemptStatus.SUBMITTED)
                .select_related('student', 'quiz', 'quiz__course')
                .order_by('-submitted_at')[:8]
            )
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
            for course in managed_courses[:8]:
                next_deadline = (
                    course.quizzes.filter(is_published=True, available_until__isnull=False)
                    .order_by('available_until')
                    .first()
                )
                course_overview.append(
                    {
                        'course': course,
                        'students': course.total_students,
                        'quizzes': course.published_quizzes_count,
                        'average_score': course.average_score,
                        'completion_rate': course.completion_rate,
                        'next_deadline': next_deadline,
                    }
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
                    },
                    'course_overview': course_overview,
                    'recent_attempts': recent_attempts,
                    'recent_announcements': (
                        Announcement.objects.filter(course__owner=user)
                        .select_related('course')
                        .order_by('-is_important', '-published_at')[:6]
                    ),
                }
            )
        else:
            enrollments = Enrollment.objects.filter(student=user).select_related('course', 'course__owner')
            recent_attempts = (
                Attempt.objects.filter(student=user, status=AttemptStatus.SUBMITTED)
                .select_related('quiz', 'quiz__course')
                .order_by('-submitted_at')[:8]
            )
            average_score = (
                Attempt.objects.filter(student=user, status=AttemptStatus.SUBMITTED)
                .aggregate(avg=Avg('score_percent'))['avg']
                or 0
            )
            progress_rows = []
            pending_quizzes_total = 0

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
                    },
                    'course_progress': progress_rows,
                    'recent_attempts': recent_attempts,
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
        else:
            context['student_progress'] = build_student_progress(course, user)
            context['topic_diagnostics'] = build_student_topic_diagnostics(course, user)

        return context


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
        return super().form_valid(form)

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
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Редактирование теста "{self.object.title}"'
        context['course'] = self.object.course
        return context

    def get_success_url(self):
        return reverse('testing:quiz_detail', kwargs={'pk': self.object.pk})


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

        context.update(
            {
                'can_manage': can_manage,
                'is_enrolled': is_enrolled,
                'remaining_attempts': quiz.remaining_attempts(user) if is_enrolled else 0,
                'submitted_attempts': submitted_attempts,
                'in_progress_attempt': in_progress_attempt,
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

            attempt = Attempt.objects.create(quiz=quiz, student=request.user)

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

    def get(self, request, *args, **kwargs):
        attempt = self.get_attempt()
        if attempt.status == AttemptStatus.SUBMITTED:
            return redirect('testing:attempt_result', pk=attempt.pk)

        form = AttemptForm(quiz=attempt.quiz)
        return render(
            request,
            self.template_name,
            {
                'attempt': attempt,
                'quiz': attempt.quiz,
                'form': form,
                'deadline_at': attempt.deadline_at,
            },
        )

    def post(self, request, *args, **kwargs):
        attempt = self.get_attempt()
        if attempt.status == AttemptStatus.SUBMITTED:
            return redirect('testing:attempt_result', pk=attempt.pk)

        form = AttemptForm(request.POST, quiz=attempt.quiz)
        if form.is_valid():
            submit_attempt(attempt, form.get_answers_mapping())
            messages.success(request, 'Тест завершен, результат сохранен.')
            return redirect('testing:attempt_result', pk=attempt.pk)

        return render(
            request,
            self.template_name,
            {
                'attempt': attempt,
                'quiz': attempt.quiz,
                'form': form,
                'deadline_at': attempt.deadline_at,
            },
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
        context['topic_insights'] = build_attempt_topic_insights(self.object)
        return context


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
        return (
            Attempt.objects.filter(quiz=self.quiz, status=AttemptStatus.SUBMITTED)
            .select_related('student')
            .order_by('-submitted_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['quiz'] = self.quiz
        context['analytics'] = {
            'attempts': self.quiz.submitted_attempts_count,
            'average_score': self.quiz.average_score,
            'pass_rate': self.quiz.pass_rate,
        }
        return context
