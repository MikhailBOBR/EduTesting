from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView, UpdateView

from testing.models import Attempt, Course, Enrollment

from .forms import ProfileUpdateForm, SignUpForm, UserAuthenticationForm


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'accounts/signup.html'
    success_url = reverse_lazy('accounts:login')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            'Аккаунт создан. Теперь вы можете войти в систему и приступить к работе.',
        )
        return response


class UserLoginView(LoginView):
    authentication_form = UserAuthenticationForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, 'Вы успешно вошли в систему.')
        return super().form_valid(form)


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if user.is_student:
            context['courses_count'] = Enrollment.objects.filter(student=user).count()
            context['tests_count'] = Attempt.objects.filter(
                student=user,
                status='submitted',
            ).count()
            context['recent_activity'] = (
                Attempt.objects.filter(student=user)
                .select_related('quiz', 'quiz__course')
                .order_by('-created_at')[:5]
            )
        else:
            context['courses_count'] = Course.objects.filter(owner=user).count()
            context['tests_count'] = Attempt.objects.filter(
                quiz__course__owner=user,
                status='submitted',
            ).count()
            context['recent_activity'] = (
                Attempt.objects.filter(quiz__course__owner=user, status='submitted')
                .select_related('student', 'quiz', 'quiz__course')
                .order_by('-submitted_at')[:5]
            )

        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    form_class = ProfileUpdateForm
    template_name = 'accounts/profile_form.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Профиль обновлён.')
        return super().form_valid(form)
