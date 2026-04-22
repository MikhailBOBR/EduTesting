from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView, UpdateView

from testing.models import Attempt, Course, Enrollment

from .forms import (
    ProfileUpdateForm,
    SignUpForm,
    UserAuthenticationForm,
    UserPasswordChangeForm,
)
from .security import (
    get_client_ip,
    get_login_lockout_remaining_seconds,
    register_failed_login,
    reset_failed_logins,
)


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

    def post(self, request, *args, **kwargs):
        username = request.POST.get('username', '')
        remaining = get_login_lockout_remaining_seconds(username, get_client_ip(request))
        if remaining > 0:
            form = self.get_form()
            form.add_error(None, f'Слишком много неудачных попыток входа. Повторите через {remaining} сек.')
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        reset_failed_logins(form.cleaned_data.get('username', ''), get_client_ip(self.request))
        messages.success(self.request, 'Вы успешно вошли в систему.')
        return super().form_valid(form)

    def form_invalid(self, form):
        username = self.request.POST.get('username', '')
        if username:
            state = register_failed_login(username, get_client_ip(self.request))
            if state.get('blocked_until'):
                remaining = get_login_lockout_remaining_seconds(username, get_client_ip(self.request))
                form.add_error(None, f'Слишком много неудачных попыток входа. Повторите через {remaining} сек.')
        return super().form_invalid(form)


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
        messages.success(self.request, 'Профиль обновлен.')
        return super().form_valid(form)


class UserPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    form_class = UserPasswordChangeForm
    template_name = 'accounts/password_change_form.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        messages.success(self.request, 'Пароль обновлен. Активная сессия сохранена.')
        return super().form_valid(form)
