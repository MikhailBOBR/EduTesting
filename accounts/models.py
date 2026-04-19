from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    STUDENT = 'student', 'Студент'
    TEACHER = 'teacher', 'Преподаватель'


class User(AbstractUser):
    email = models.EmailField('Электронная почта', unique=True)
    role = models.CharField(
        'Роль',
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
    )
    academic_group = models.CharField('Учебная группа', max_length=120, blank=True)
    bio = models.TextField('О пользователе', blank=True)

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    @property
    def is_student(self):
        return self.role == UserRole.STUDENT

    @property
    def is_teacher(self):
        return self.role == UserRole.TEACHER
