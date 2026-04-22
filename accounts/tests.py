from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from testing.models import Attempt, AttemptStatus, Course, Enrollment, Quiz

from .models import User, UserRole


class AccountsBaseMixin:
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            username='teacher',
            email='teacher@example.com',
            password='TeacherPass123!',
            first_name='Anna',
            last_name='Teacher',
            role=UserRole.TEACHER,
        )
        cls.student = User.objects.create_user(
            username='student',
            email='student@example.com',
            password='StudentPass123!',
            first_name='Ivan',
            last_name='Student',
            role=UserRole.STUDENT,
            academic_group='IS-21',
        )
        cls.course = Course.objects.create(
            title='Backend Basics',
            subject_code='WEB-101',
            summary='Introductory backend course.',
            description='Course about Django views, models and tests.',
            audience='Third-year students',
            owner=cls.teacher,
            is_published=True,
        )
        Enrollment.objects.create(course=cls.course, student=cls.student)
        cls.quiz = Quiz.objects.create(
            course=cls.course,
            title='HTTP and Django',
            description='Short test about request handling.',
            is_published=True,
        )
        cls.submitted_attempt = Attempt.objects.create(
            quiz=cls.quiz,
            student=cls.student,
            status=AttemptStatus.SUBMITTED,
            submitted_at=timezone.now(),
            score_points=8,
            score_percent=80,
            correct_answers_count=4,
        )

    def setUp(self):
        cache.clear()


class SignUpViewTests(AccountsBaseMixin, TestCase):
    def test_signup_creates_student_account(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'new_student',
                'email': 'new_student@example.com',
                'first_name': 'New',
                'last_name': 'Student',
                'role': UserRole.STUDENT,
                'academic_group': 'IS-31',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
        )

        self.assertRedirects(response, reverse('accounts:login'))
        user = User.objects.get(username='new_student')
        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertEqual(user.academic_group, 'IS-31')
        self.assertNotEqual(user.password, 'StrongPass123!')
        self.assertTrue(user.check_password('StrongPass123!'))

    def test_signup_rejects_duplicate_email(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'duplicate_email',
                'email': 'student@example.com',
                'first_name': 'Copy',
                'last_name': 'Student',
                'role': UserRole.STUDENT,
                'academic_group': 'IS-32',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('email', response.context['form'].errors)
        self.assertEqual(User.objects.filter(email='student@example.com').count(), 1)


class AuthenticationAndProfileTests(AccountsBaseMixin, TestCase):
    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:profile')}")

    def test_authenticated_user_visiting_login_is_redirected_to_dashboard(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('accounts:login'))
        self.assertRedirects(response, reverse('testing:dashboard'))

    def test_authenticated_user_can_update_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('accounts:profile_edit'),
            {
                'first_name': 'Anna',
                'last_name': 'Teacher',
                'email': 'teacher@example.com',
                'academic_group': 'Teachers',
                'bio': 'Curator of backend disciplines.',
            },
        )

        self.assertRedirects(response, reverse('accounts:profile'))
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.academic_group, 'Teachers')
        self.assertEqual(self.teacher.bio, 'Curator of backend disciplines.')

    def test_authenticated_user_can_change_password(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('accounts:password_change'),
            {
                'old_password': 'StudentPass123!',
                'new_password1': 'StudentPass456!',
                'new_password2': 'StudentPass456!',
            },
        )

        self.assertRedirects(response, reverse('accounts:profile'))
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('StudentPass456!'))

    def test_login_is_temporarily_blocked_after_repeated_failures(self):
        login_url = reverse('accounts:login')

        for _ in range(5):
            self.client.post(
                login_url,
                {
                    'username': self.student.username,
                    'password': 'WrongPassword123!',
                },
            )

        blocked_response = self.client.post(
            login_url,
            {
                'username': self.student.username,
                'password': 'StudentPass123!',
            },
        )

        self.assertEqual(blocked_response.status_code, 200)
        self.assertContains(blocked_response, 'Слишком много неудачных попыток входа')

    def test_student_profile_context_contains_counts_and_recent_activity(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('accounts:profile'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['courses_count'], 1)
        self.assertEqual(response.context['tests_count'], 1)
        self.assertEqual(len(response.context['recent_activity']), 1)

    def test_teacher_profile_context_contains_counts_and_recent_activity(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('accounts:profile'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['courses_count'], 1)
        self.assertEqual(response.context['tests_count'], 1)
        self.assertEqual(len(response.context['recent_activity']), 1)

    def test_staff_profile_shows_admin_link(self):
        self.teacher.is_staff = True
        self.teacher.save(update_fields=['is_staff'])
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('accounts:profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin:index'))
