from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .models import UserRole


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    required_role = None
    raise_exception = True

    def test_func(self):
        return self.request.user.role == self.required_role

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, 'У вас нет прав для доступа к этому разделу.')
        return super().handle_no_permission()


class StudentRequiredMixin(RoleRequiredMixin):
    required_role = UserRole.STUDENT


class TeacherRequiredMixin(RoleRequiredMixin):
    required_role = UserRole.TEACHER
