import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import User, UserRole

from .analytics import (
    build_attempt_comparison,
    build_attempt_topic_insights,
    build_course_attention_students,
    build_course_leaderboard,
    build_course_topic_diagnostics,
    build_student_topic_diagnostics,
)
from .forms import AttemptForm, JoinCourseForm, QuizForm
from .models import (
    Announcement,
    Attempt,
    AttemptDraft,
    AttemptReview,
    AttemptStatus,
    Choice,
    Course,
    Enrollment,
    Question,
    QuestionType,
    Quiz,
    SemesterChoices,
    UserNotification,
)
from .services import get_attempt_draft_mapping, save_attempt_draft, submit_attempt


class TestingBaseMixin:
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.teacher = User.objects.create_user(
            username='teacher',
            email='teacher@example.com',
            password='TeacherPass123!',
            first_name='Anna',
            last_name='Teacher',
            role=UserRole.TEACHER,
        )
        cls.second_teacher = User.objects.create_user(
            username='teacher_two',
            email='teacher_two@example.com',
            password='TeacherPass123!',
            first_name='Olga',
            last_name='Reviewer',
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
        cls.other_student = User.objects.create_user(
            username='student_two',
            email='student_two@example.com',
            password='StudentPass123!',
            first_name='Maria',
            last_name='Tester',
            role=UserRole.STUDENT,
            academic_group='IS-22',
        )

        cls.course = Course.objects.create(
            title='Python and Django',
            subject_code='WEB-301',
            summary='Course about backend web development.',
            description='Study of Django architecture and student testing services.',
            audience='Third-year students',
            semester=SemesterChoices.AUTUMN,
            academic_year='2025/2026',
            assessment_policy='Score is based on tests and practice tasks.',
            owner=cls.teacher,
            is_published=True,
        )
        cls.unpublished_course = Course.objects.create(
            title='Private Teacher Course',
            subject_code='WEB-999',
            summary='Draft course.',
            description='Hidden teacher-only course.',
            audience='Teacher group',
            semester=SemesterChoices.SPRING,
            owner=cls.teacher,
            is_published=False,
        )
        cls.foreign_course = Course.objects.create(
            title='QA Fundamentals',
            subject_code='QA-401',
            summary='Independent course of another teacher.',
            description='Course for software testing basics.',
            audience='Fourth-year students',
            semester=SemesterChoices.SPRING,
            owner=cls.second_teacher,
            is_published=True,
        )

        cls.announcement = Announcement.objects.create(
            course=cls.course,
            title='Module start',
            body='Please complete the entrance test before the end of the week.',
            is_important=True,
        )
        Enrollment.objects.create(course=cls.course, student=cls.student)

        cls.quiz = Quiz.objects.create(
            course=cls.course,
            title='Django Basics',
            description='Test on core Django concepts.',
            instructions='Choose the correct answers.',
            time_limit_minutes=20,
            passing_score=60,
            max_attempts=2,
            available_from=now - timedelta(days=1),
            available_until=now + timedelta(days=1),
            show_correct_answers=True,
            is_published=True,
        )
        cls.hidden_quiz = Quiz.objects.create(
            course=cls.course,
            title='Models and ORM',
            description='Result page hides answer key from students.',
            instructions='Choose one correct answer.',
            time_limit_minutes=10,
            passing_score=60,
            max_attempts=1,
            available_from=now - timedelta(days=1),
            available_until=now + timedelta(days=1),
            show_correct_answers=False,
            is_published=True,
        )

        cls.question_single = Question.objects.create(
            quiz=cls.quiz,
            text='Which architecture pattern does Django use?',
            topic='Architecture',
            explanation='Django projects are built around MVT.',
            question_type=QuestionType.SINGLE,
            difficulty='basic',
            points=2,
            order=1,
        )
        cls.single_wrong = Choice.objects.create(
            question=cls.question_single,
            text='MVC',
            is_correct=False,
            order=1,
        )
        cls.single_correct = Choice.objects.create(
            question=cls.question_single,
            text='MVT',
            is_correct=True,
            order=2,
        )
        cls.question_multi = Question.objects.create(
            quiz=cls.quiz,
            text='What belongs to Django ORM?',
            topic='ORM',
            explanation='Migrations and the Python query API belong to ORM.',
            question_type=QuestionType.MULTIPLE,
            difficulty='intermediate',
            points=3,
            order=2,
        )
        cls.multi_correct_1 = Choice.objects.create(
            question=cls.question_multi,
            text='Migrations',
            is_correct=True,
            order=1,
        )
        cls.multi_wrong = Choice.objects.create(
            question=cls.question_multi,
            text='HTML templating only',
            is_correct=False,
            order=2,
        )
        cls.multi_correct_2 = Choice.objects.create(
            question=cls.question_multi,
            text='Python query API',
            is_correct=True,
            order=3,
        )
        cls.hidden_question = Question.objects.create(
            quiz=cls.hidden_quiz,
            text='What is stored in models.py?',
            topic='Project structure',
            explanation='This file defines data models.',
            question_type=QuestionType.SINGLE,
            difficulty='basic',
            points=1,
            order=1,
        )
        cls.hidden_choice_wrong = Choice.objects.create(
            question=cls.hidden_question,
            text='HTML templates',
            is_correct=False,
            order=1,
        )
        cls.hidden_choice_correct = Choice.objects.create(
            question=cls.hidden_question,
            text='Data models',
            is_correct=True,
            order=2,
        )

    def correct_answers(self):
        return {
            self.question_single.id: {self.single_correct.id},
            self.question_multi.id: {self.multi_correct_1.id, self.multi_correct_2.id},
        }

    def partial_answers(self):
        return {
            self.question_single.id: {self.single_correct.id},
            self.question_multi.id: {self.multi_correct_1.id},
        }

    def hidden_answers(self):
        return {
            self.hidden_question.id: {self.hidden_choice_correct.id},
        }

    def create_submitted_attempt(self, student=None, quiz=None, answers_mapping=None, minutes_ago=5):
        student = student or self.student
        quiz = quiz or self.quiz
        if answers_mapping is None:
            answers_mapping = self.hidden_answers() if quiz == self.hidden_quiz else self.correct_answers()

        attempt = Attempt.objects.create(quiz=quiz, student=student)
        Attempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=minutes_ago))
        attempt.refresh_from_db()
        submit_attempt(attempt, answers_mapping)
        attempt.refresh_from_db()
        return attempt


class ModelAndFormTests(TestingBaseMixin, TestCase):
    def test_course_generates_access_code_on_save(self):
        self.assertEqual(len(self.course.access_code), 8)
        self.assertTrue(self.course.access_code.isalnum())
        self.assertEqual(self.course.access_code, self.course.access_code.upper())

    def test_course_clean_rejects_invalid_date_range(self):
        course = Course(
            title='Dates',
            summary='Dates test',
            description='Description',
            owner=self.teacher,
            start_date=timezone.now().date(),
            end_date=(timezone.now() - timedelta(days=1)).date(),
        )

        with self.assertRaises(ValidationError):
            course.full_clean()

    def test_quiz_form_rejects_invalid_availability_range(self):
        form = QuizForm(
            data={
                'title': 'Broken window',
                'description': 'Description',
                'instructions': 'Instructions',
                'time_limit_minutes': 15,
                'passing_score': 60,
                'max_attempts': 1,
                'available_from': '2026-01-10T12:00',
                'available_until': '2026-01-09T12:00',
                'show_correct_answers': True,
                'is_published': True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('available_until', form.errors)

    def test_join_course_form_normalizes_access_code(self):
        form = JoinCourseForm(data={'access_code': f'  {self.course.access_code.lower()}  '})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['access_code'], self.course.access_code)

    def test_attempt_form_builds_answers_mapping(self):
        form = AttemptForm(
            data={
                f'question_{self.question_single.id}': str(self.single_correct.id),
                f'question_{self.question_multi.id}': [
                    str(self.multi_correct_1.id),
                    str(self.multi_correct_2.id),
                ],
            },
            quiz=self.quiz,
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_answers_mapping(), self.correct_answers())

    def test_quiz_and_course_metrics_reflect_submitted_attempts(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student)
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.partial_answers())

        self.assertEqual(self.quiz.submitted_attempts_count, 2)
        self.assertEqual(self.quiz.average_score, 70)
        self.assertEqual(self.quiz.pass_rate, 50)
        self.assertEqual(self.course.average_score, 70)
        self.assertEqual(self.course.completion_rate, 100)

    def test_quiz_remaining_attempts_counts_only_submitted_attempts(self):
        self.create_submitted_attempt(student=self.student)
        Attempt.objects.create(quiz=self.quiz, student=self.student, status=AttemptStatus.IN_PROGRESS)

        self.assertEqual(self.quiz.remaining_attempts(self.student), 1)

    def test_unanswered_configuration_count_counts_questions_without_correct_choice(self):
        question = Question.objects.create(
            quiz=self.quiz,
            text='Question without correct answer',
            question_type=QuestionType.SINGLE,
            points=1,
            order=3,
        )
        Choice.objects.create(question=question, text='Wrong option', is_correct=False, order=1)

        self.assertEqual(self.quiz.unanswered_configuration_count, 1)

    def test_single_choice_question_rejects_second_correct_option(self):
        duplicate_correct = Choice(
            question=self.question_single,
            text='MTV',
            is_correct=True,
            order=3,
        )

        with self.assertRaises(ValidationError):
            duplicate_correct.full_clean()


class ServiceTests(TestingBaseMixin, TestCase):
    def test_submit_attempt_calculates_full_score_and_duration(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)
        Attempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=7))
        attempt.refresh_from_db()

        submit_attempt(attempt, self.correct_answers())

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.SUBMITTED)
        self.assertEqual(attempt.score_points, 5)
        self.assertEqual(attempt.score_percent, 100)
        self.assertEqual(attempt.correct_answers_count, 2)
        self.assertGreaterEqual(attempt.duration_seconds, 0)
        self.assertTrue(attempt.is_passed)

    def test_submit_attempt_ignores_invalid_choice_ids_and_requires_exact_match(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)

        submit_attempt(
            attempt,
            {
                self.question_single.id: {self.single_correct.id},
                self.question_multi.id: {self.multi_correct_1.id, 999999},
            },
        )

        attempt.refresh_from_db()
        self.assertEqual(attempt.score_points, 2)
        self.assertEqual(attempt.score_percent, 40)
        self.assertEqual(attempt.correct_answers_count, 1)

    def test_submit_attempt_replaces_previous_answers_on_resubmission(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)
        submit_attempt(attempt, self.partial_answers())
        attempt.refresh_from_db()

        self.assertEqual(attempt.answers.count(), 2)
        self.assertEqual(attempt.score_percent, 40)

        submit_attempt(attempt, self.correct_answers())
        attempt.refresh_from_db()

        self.assertEqual(attempt.answers.count(), 2)
        self.assertEqual(attempt.score_percent, 100)
        self.assertEqual(attempt.correct_answers_count, 2)

    def test_save_attempt_draft_normalizes_answers_and_restores_mapping(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)

        draft = save_attempt_draft(
            attempt,
            {
                str(self.question_single.id): [self.single_correct.id],
                str(self.question_multi.id): [self.multi_correct_1.id, 999999],
            },
            last_question_id=str(self.question_multi.id),
        )

        self.assertEqual(draft.answered_questions_count, 2)
        self.assertEqual(
            get_attempt_draft_mapping(attempt),
            {
                self.question_single.id: {self.single_correct.id},
                self.question_multi.id: {self.multi_correct_1.id},
            },
        )
        self.assertEqual(draft.last_question_id, self.question_multi.id)

    def test_submit_attempt_clears_draft_after_submission(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)
        save_attempt_draft(attempt, self.partial_answers())

        submit_attempt(attempt, self.correct_answers())

        self.assertFalse(AttemptDraft.objects.filter(attempt=attempt).exists())
        self.assertTrue(
            UserNotification.objects.filter(
                recipient=self.teacher,
                category='attempt',
                attempt=attempt,
            ).exists()
        )


class AnalyticsTests(TestingBaseMixin, TestCase):
    def test_build_student_topic_diagnostics_identifies_weak_topic(self):
        self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())

        diagnostics = build_student_topic_diagnostics(self.course, self.student)

        self.assertEqual(diagnostics['overall_accuracy'], 50)
        self.assertEqual(diagnostics['topic_rows'][0]['topic'], 'ORM')
        self.assertEqual(diagnostics['topic_rows'][0]['status_code'], 'risk')
        self.assertTrue(diagnostics['recommendations'])

    def test_build_course_topic_diagnostics_aggregates_topic_statistics(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.correct_answers())

        diagnostics = build_course_topic_diagnostics(self.course)

        orm_row = next(row for row in diagnostics['topic_rows'] if row['topic'] == 'ORM')
        self.assertEqual(diagnostics['overall_accuracy'], 75)
        self.assertEqual(orm_row['students_count'], 2)
        self.assertEqual(orm_row['attempts_count'], 2)
        self.assertEqual(orm_row['accuracy_percent'], 50)

    def test_build_course_attention_students_prioritizes_problem_student(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.correct_answers())

        rows = build_course_attention_students(self.course)

        self.assertEqual(rows[0]['student'], self.student)
        self.assertEqual(rows[0]['status_code'], 'risk')
        self.assertEqual(rows[0]['weakest_topic'], 'ORM')

    def test_build_attempt_topic_insights_returns_strongest_and_weakest_topics(self):
        attempt = self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())

        insights = build_attempt_topic_insights(attempt)

        self.assertEqual(insights['weakest_topic']['topic'], 'ORM')
        self.assertEqual(insights['strongest_topic']['topic'], 'Architecture')
        self.assertTrue(insights['recommendations'])

    def test_build_course_leaderboard_sorts_students_by_average_score(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student, answers_mapping=self.correct_answers())
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.partial_answers())

        leaderboard = build_course_leaderboard(self.course)

        self.assertEqual(leaderboard[0]['student'], self.student)
        self.assertEqual(leaderboard[0]['rank'], 1)
        self.assertGreater(leaderboard[0]['average_score'], leaderboard[1]['average_score'])

    def test_build_attempt_comparison_returns_delta_against_previous_attempt(self):
        first_attempt = self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())
        second_attempt = self.create_submitted_attempt(student=self.student, answers_mapping=self.correct_answers())

        comparison = build_attempt_comparison(second_attempt)

        self.assertEqual(comparison['previous_attempt'], first_attempt)
        self.assertEqual(comparison['score_delta'], 60)
        self.assertEqual(comparison['correct_answers_delta'], 1)
        self.assertEqual(comparison['improved_topics'][0]['topic'], 'ORM')


class CourseAndDashboardViewTests(TestingBaseMixin, TestCase):
    def test_course_list_hides_unpublished_course_for_guest(self):
        response = self.client.get(reverse('testing:course_list'))
        course_ids = {course.pk for course in response.context['courses']}

        self.assertIn(self.course.pk, course_ids)
        self.assertNotIn(self.unpublished_course.pk, course_ids)

    def test_course_list_shows_teacher_own_unpublished_course(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('testing:course_list'))
        course_ids = {course.pk for course in response.context['courses']}

        self.assertIn(self.course.pk, course_ids)
        self.assertIn(self.unpublished_course.pk, course_ids)

    def test_course_list_filters_by_query_and_semester(self):
        spring_course = Course.objects.create(
            title='Spring Databases',
            subject_code='DB-210',
            summary='Course about SQL.',
            description='Database design and queries.',
            semester=SemesterChoices.SPRING,
            owner=self.teacher,
            is_published=True,
        )

        response = self.client.get(reverse('testing:course_list'), {'q': 'spring', 'semester': SemesterChoices.SPRING})
        courses = list(response.context['courses'])

        self.assertEqual(courses, [spring_course])

    def test_course_detail_returns_404_for_unpublished_course_to_student(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('testing:course_detail', args=[self.unpublished_course.pk]))
        self.assertEqual(response.status_code, 404)

    def test_course_detail_for_enrolled_student_includes_progress_context(self):
        self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:course_detail', args=[self.course.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_enrolled'])
        self.assertEqual(response.context['student_progress']['completed_quizzes'], 1)
        self.assertEqual(response.context['student_progress']['pending_quizzes'], 1)

    def test_course_detail_for_teacher_includes_student_rows(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('testing:course_detail', args=[self.course.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_manage'])
        self.assertEqual(len(response.context['student_rows']), 1)

    def test_student_can_open_course_insights_page_when_enrolled(self):
        self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:course_insights', args=[self.course.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_manage'])
        self.assertEqual(response.context['topic_diagnostics']['topic_rows'][0]['topic'], 'ORM')

    def test_teacher_can_open_course_insights_page(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student)
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.partial_answers())
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('testing:course_insights', args=[self.course.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_manage'])
        self.assertTrue(response.context['attention_students'])
        self.assertEqual(response.context['leaderboard'][0]['student'], self.student)

    def test_unenrolled_student_cannot_open_course_insights_page(self):
        self.client.force_login(self.other_student)

        response = self.client.get(reverse('testing:course_insights', args=[self.course.pk]))

        self.assertEqual(response.status_code, 403)

    def test_student_dashboard_shows_progress_summary(self):
        self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['courses'], 1)
        self.assertEqual(response.context['summary']['completed_quizzes'], 1)
        self.assertEqual(response.context['summary']['average_score'], 100)
        self.assertEqual(response.context['summary']['pending_quizzes'], 1)

    def test_teacher_dashboard_shows_management_summary(self):
        self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('testing:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['courses'], 2)
        self.assertEqual(response.context['summary']['students'], 1)
        self.assertEqual(response.context['summary']['attempts'], 1)
        self.assertEqual(response.context['summary']['average_score'], 100)

    def test_dashboard_and_notification_center_show_recent_notifications(self):
        attempt = self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.teacher)

        dashboard_response = self.client.get(reverse('testing:dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(dashboard_response.context['summary']['unread_notifications'], 1)
        self.assertEqual(dashboard_response.context['recent_notifications'][0].attempt, attempt)

        notifications_response = self.client.get(reverse('testing:notifications'))
        self.assertEqual(notifications_response.status_code, 200)
        self.assertContains(notifications_response, attempt.quiz.title)

    def test_user_can_mark_notification_as_read(self):
        attempt = self.create_submitted_attempt(student=self.student)
        notification = UserNotification.objects.get(attempt=attempt, recipient=self.teacher)
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('testing:notification_mark_read', args=[notification.pk]),
            {'next': reverse('testing:notifications')},
        )

        self.assertRedirects(response, reverse('testing:notifications'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)


class StudentFlowTests(TestingBaseMixin, TestCase):
    def test_student_can_start_and_submit_quiz(self):
        self.client.force_login(self.student)
        start_response = self.client.post(reverse('testing:quiz_start', args=[self.quiz.pk]))

        attempt = Attempt.objects.get(quiz=self.quiz, student=self.student, status=AttemptStatus.IN_PROGRESS)
        self.assertRedirects(start_response, reverse('testing:attempt_detail', args=[attempt.pk]))

        result_response = self.client.post(
            reverse('testing:attempt_detail', args=[attempt.pk]),
            {
                f'question_{self.question_single.id}': str(self.single_correct.id),
                f'question_{self.question_multi.id}': [
                    str(self.multi_correct_1.id),
                    str(self.multi_correct_2.id),
                ],
            },
        )

        self.assertRedirects(result_response, reverse('testing:attempt_result', args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.score_percent, 100)

    def test_start_attempt_reuses_existing_in_progress_attempt(self):
        existing_attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)
        self.client.force_login(self.student)

        response = self.client.post(reverse('testing:quiz_start', args=[self.quiz.pk]))

        self.assertRedirects(response, reverse('testing:attempt_detail', args=[existing_attempt.pk]))
        self.assertEqual(
            Attempt.objects.filter(quiz=self.quiz, student=self.student, status=AttemptStatus.IN_PROGRESS).count(),
            1,
        )

    def test_student_cannot_start_quiz_without_enrollment(self):
        foreign_quiz = Quiz.objects.create(
            course=self.foreign_course,
            title='Foreign quiz',
            is_published=True,
            available_from=timezone.now() - timedelta(days=1),
            available_until=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.student)

        response = self.client.post(reverse('testing:quiz_start', args=[foreign_quiz.pk]))

        self.assertRedirects(response, reverse('testing:course_detail', args=[self.foreign_course.pk]))
        self.assertFalse(Attempt.objects.filter(quiz=foreign_quiz, student=self.student).exists())

    def test_student_cannot_start_unavailable_quiz(self):
        future_quiz = Quiz.objects.create(
            course=self.course,
            title='Future quiz',
            is_published=True,
            available_from=timezone.now() + timedelta(days=2),
            available_until=timezone.now() + timedelta(days=3),
        )
        question = Question.objects.create(
            quiz=future_quiz,
            text='Future question',
            question_type=QuestionType.SINGLE,
            points=1,
            order=1,
        )
        Choice.objects.create(question=question, text='Answer', is_correct=True, order=1)
        self.client.force_login(self.student)

        response = self.client.post(reverse('testing:quiz_start', args=[future_quiz.pk]))

        self.assertRedirects(response, reverse('testing:quiz_detail', args=[future_quiz.pk]))
        self.assertFalse(Attempt.objects.filter(quiz=future_quiz, student=self.student).exists())

    def test_student_cannot_start_quiz_without_questions(self):
        empty_quiz = Quiz.objects.create(
            course=self.course,
            title='Empty quiz',
            is_published=True,
            available_from=timezone.now() - timedelta(days=1),
            available_until=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.student)

        response = self.client.post(reverse('testing:quiz_start', args=[empty_quiz.pk]))

        self.assertRedirects(response, reverse('testing:quiz_detail', args=[empty_quiz.pk]))

    def test_student_cannot_start_quiz_with_unconfigured_question(self):
        broken_quiz = Quiz.objects.create(
            course=self.course,
            title='Broken quiz',
            is_published=True,
            available_from=timezone.now() - timedelta(days=1),
            available_until=timezone.now() + timedelta(days=1),
        )
        broken_question = Question.objects.create(
            quiz=broken_quiz,
            text='Broken question',
            question_type=QuestionType.SINGLE,
            points=1,
            order=1,
        )
        Choice.objects.create(question=broken_question, text='Wrong option', is_correct=False, order=1)
        self.client.force_login(self.student)

        response = self.client.post(reverse('testing:quiz_start', args=[broken_quiz.pk]))

        self.assertRedirects(response, reverse('testing:quiz_detail', args=[broken_quiz.pk]))
        self.assertFalse(Attempt.objects.filter(quiz=broken_quiz, student=self.student).exists())

    def test_student_cannot_start_quiz_after_attempt_limit(self):
        self.create_submitted_attempt(student=self.student)
        self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.student)

        response = self.client.post(reverse('testing:quiz_start', args=[self.quiz.pk]))

        self.assertRedirects(response, reverse('testing:quiz_detail', args=[self.quiz.pk]))
        self.assertEqual(
            Attempt.objects.filter(quiz=self.quiz, student=self.student, status=AttemptStatus.IN_PROGRESS).count(),
            0,
        )

    def test_student_can_join_course_by_access_code(self):
        self.client.force_login(self.other_student)
        response = self.client.post(
            reverse('testing:course_join_by_code'),
            {'access_code': self.course.access_code.lower()},
        )

        self.assertRedirects(response, reverse('testing:course_detail', args=[self.course.pk]))
        self.assertTrue(Enrollment.objects.filter(course=self.course, student=self.other_student).exists())

    def test_join_course_with_invalid_code_does_not_create_enrollment(self):
        self.client.force_login(self.other_student)
        response = self.client.post(reverse('testing:course_join_by_code'), {'access_code': 'WRONG123'})

        self.assertRedirects(response, reverse('testing:dashboard'))
        self.assertFalse(Enrollment.objects.filter(course=self.course, student=self.other_student).exists())

    def test_student_can_enroll_via_course_endpoint(self):
        self.client.force_login(self.other_student)
        response = self.client.post(reverse('testing:course_enroll', args=[self.course.pk]))

        self.assertRedirects(response, reverse('testing:course_detail', args=[self.course.pk]))
        self.assertTrue(Enrollment.objects.filter(course=self.course, student=self.other_student).exists())

    def test_attempt_detail_redirects_submitted_attempt_to_result(self):
        attempt = self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:attempt_detail', args=[attempt.pk]))

        self.assertRedirects(response, reverse('testing:attempt_result', args=[attempt.pk]))

    def test_student_can_autosave_attempt_draft_via_view(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('testing:attempt_draft', args=[attempt.pk]),
            data=json.dumps(
                {
                    'answers': {
                        str(self.question_single.id): [self.single_correct.id],
                        str(self.question_multi.id): [self.multi_correct_1.id],
                    },
                    'last_question_id': self.question_multi.id,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['answered_questions_count'], 2)
        self.assertTrue(AttemptDraft.objects.filter(attempt=attempt).exists())

    def test_attempt_detail_restores_saved_draft_answers(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)
        save_attempt_draft(attempt, self.partial_answers(), last_question_id=self.question_multi.id)
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:attempt_detail', args=[attempt.pk]))

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form[AttemptForm.get_field_name(self.question_single.id)].value(), str(self.single_correct.id))
        self.assertEqual(
            form[AttemptForm.get_field_name(self.question_multi.id)].value(),
            [str(self.multi_correct_1.id)],
        )

    def test_attempt_result_includes_comparison_context(self):
        self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())
        second_attempt = self.create_submitted_attempt(student=self.student, answers_mapping=self.correct_answers())
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:attempt_result', args=[second_attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['attempt_comparison']['score_delta'], 60)
        self.assertEqual(response.context['attempt_comparison']['improved_topics'][0]['topic'], 'ORM')

    def test_student_cannot_view_other_students_attempt(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        attempt = self.create_submitted_attempt(student=self.other_student)
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:attempt_result', args=[attempt.pk]))

        self.assertEqual(response.status_code, 403)

    def test_student_sees_hidden_answer_key_flag_in_result_context(self):
        attempt = self.create_submitted_attempt(student=self.student, quiz=self.hidden_quiz)
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:attempt_result', args=[attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_answer_key'])
        self.assertEqual(response.context['topic_insights']['weakest_topic']['topic'], 'Project structure')

    def test_teacher_still_sees_hidden_answer_key_in_result_context(self):
        attempt = self.create_submitted_attempt(student=self.student, quiz=self.hidden_quiz)
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('testing:attempt_result', args=[attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_answer_key'])

    def test_student_sees_teacher_feedback_on_attempt_result(self):
        attempt = self.create_submitted_attempt(student=self.student)
        AttemptReview.objects.create(
            attempt=attempt,
            teacher=self.teacher,
            feedback='Нужно повторить тему ORM и еще раз пройти практику.',
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse('testing:attempt_result', args=[attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Нужно повторить тему ORM')


class TeacherManagementTests(TestingBaseMixin, TestCase):
    def test_teacher_can_create_course(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('testing:course_create'),
            {
                'title': 'Databases',
                'subject_code': 'DB-210',
                'summary': 'SQL and design',
                'description': 'Course on databases and schema design.',
                'audience': 'Second-year students',
                'semester': SemesterChoices.SPRING,
                'academic_year': '2025/2026',
                'assessment_policy': 'Score is based on labs and quizzes.',
                'is_published': True,
            },
        )

        created_course = Course.objects.get(title='Databases')
        self.assertRedirects(response, reverse('testing:course_detail', args=[created_course.pk]))
        self.assertEqual(created_course.owner, self.teacher)
        self.assertEqual(created_course.subject_code, 'DB-210')

    def test_teacher_can_publish_announcement(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('testing:announcement_create', args=[self.course.pk]),
            {
                'title': 'Deadline update',
                'body': 'The quiz deadline is extended until Sunday.',
                'is_important': True,
            },
        )

        self.assertRedirects(response, reverse('testing:course_detail', args=[self.course.pk]))
        self.assertTrue(Announcement.objects.filter(course=self.course, title='Deadline update').exists())
        self.assertTrue(
            UserNotification.objects.filter(
                recipient=self.student,
                category='announcement',
                title__contains='Deadline update',
            ).exists()
        )

    def test_teacher_can_create_quiz(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('testing:quiz_create', args=[self.course.pk]),
            {
                'title': 'Deployment basics',
                'description': 'Questions about deployment.',
                'instructions': 'Choose the correct option.',
                'time_limit_minutes': 25,
                'passing_score': 70,
                'max_attempts': 3,
                'available_from': '',
                'available_until': '',
                'show_correct_answers': True,
                'is_published': True,
            },
        )

        quiz = Quiz.objects.get(title='Deployment basics')
        self.assertRedirects(response, reverse('testing:quiz_detail', args=[quiz.pk]))
        self.assertEqual(quiz.course, self.course)
        self.assertTrue(
            UserNotification.objects.filter(
                recipient=self.student,
                category='quiz',
                title__contains='Deployment basics',
            ).exists()
        )

    def test_teacher_can_view_quiz_attempts_analytics(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student)
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.partial_answers())
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('testing:quiz_attempts', args=[self.quiz.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['analytics']['attempts'], 2)
        self.assertEqual(response.context['analytics']['average_score'], 70)
        self.assertEqual(response.context['analytics']['pass_rate'], 50)

    def test_teacher_can_view_student_attempt_result_for_owned_course(self):
        attempt = self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('testing:attempt_result', args=[attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['attempt'].pk, attempt.pk)

    def test_teacher_can_add_feedback_to_attempt(self):
        attempt = self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('testing:attempt_review', args=[attempt.pk]),
            {'feedback': 'Хорошая работа, но нужно закрепить тему ORM.'},
        )

        self.assertRedirects(response, reverse('testing:attempt_result', args=[attempt.pk]))
        review = AttemptReview.objects.get(attempt=attempt)
        self.assertEqual(review.teacher, self.teacher)
        self.assertIn('ORM', review.feedback)
        self.assertTrue(
            UserNotification.objects.filter(
                recipient=self.student,
                category='review',
                attempt=attempt,
            ).exists()
        )

    def test_teacher_can_export_course_results_csv(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student)
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.partial_answers())
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('testing:course_export_csv', args=[self.course.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8-sig')
        self.assertIn(self.quiz.title, content)
        self.assertIn(self.student.username, content)

    def test_student_cannot_open_teacher_course_creation_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('testing:course_create'))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_export_course_results_csv(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('testing:course_export_csv', args=[self.course.pk]))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_open_quiz_attempts_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('testing:quiz_attempts', args=[self.quiz.pk]))
        self.assertEqual(response.status_code, 404)

    def test_other_teacher_cannot_edit_foreign_course(self):
        self.client.force_login(self.second_teacher)
        response = self.client.get(reverse('testing:course_edit', args=[self.course.pk]))
        self.assertEqual(response.status_code, 404)

    def test_other_teacher_cannot_view_student_attempt_result_for_foreign_course(self):
        attempt = self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.second_teacher)

        response = self.client.get(reverse('testing:attempt_result', args=[attempt.pk]))

        self.assertEqual(response.status_code, 403)

    def test_other_teacher_cannot_review_foreign_attempt(self):
        attempt = self.create_submitted_attempt(student=self.student)
        self.client.force_login(self.second_teacher)

        response = self.client.get(reverse('testing:attempt_review', args=[attempt.pk]))

        self.assertEqual(response.status_code, 404)


class ApiTests(TestingBaseMixin, TestCase):
    def auth_headers(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        return {'HTTP_AUTHORIZATION': f'Token {token.key}'}

    def test_api_token_auth_returns_token_and_user(self):
        response = self.client.post(
            reverse('testing_api:token_auth'),
            {'username': self.student.username, 'password': 'StudentPass123!'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('token', data)
        self.assertEqual(data['user']['username'], self.student.username)
        self.assertEqual(data['user']['role'], UserRole.STUDENT)

    def test_api_me_requires_authentication(self):
        unauthorized = self.client.get(reverse('testing_api:me'))
        authorized = self.client.get(reverse('testing_api:me'), **self.auth_headers(self.student))

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json()['username'], self.student.username)

    def test_api_stats_returns_expected_keys(self):
        self.create_submitted_attempt(student=self.student)

        response = self.client.get(reverse('testing_api:stats'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['courses'], 2)
        self.assertEqual(data['quizzes'], 2)
        self.assertEqual(data['students'], 1)
        self.assertEqual(data['submitted_attempts'], 1)
        self.assertEqual(data['announcements'], 1)

    def test_api_course_list_returns_only_published_courses(self):
        response = self.client.get(reverse('testing_api:course_list'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {item['title'] for item in data}

        self.assertIn(self.course.title, titles)
        self.assertIn(self.foreign_course.title, titles)
        self.assertNotIn(self.unpublished_course.title, titles)

    def test_api_course_detail_includes_quizzes_and_announcements(self):
        response = self.client.get(reverse('testing_api:course_detail', args=[self.course.pk]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['title'], self.course.title)
        self.assertEqual(len(data['quizzes']), 2)
        self.assertEqual(len(data['announcements']), 1)
        self.assertEqual(data['announcements'][0]['title'], self.announcement.title)

    def test_api_my_courses_returns_student_enrollments(self):
        response = self.client.get(reverse('testing_api:my_course_list'), **self.auth_headers(self.student))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], self.course.pk)
        self.assertEqual(data[0]['my_role'], UserRole.STUDENT)

    def test_api_student_can_enroll_start_and_submit_attempt(self):
        Enrollment.objects.filter(course=self.course, student=self.student).delete()

        enroll_response = self.client.post(
            reverse('testing_api:course_enroll', args=[self.course.pk]),
            {},
            content_type='application/json',
            **self.auth_headers(self.student),
        )
        self.assertEqual(enroll_response.status_code, 201)
        self.assertTrue(Enrollment.objects.filter(course=self.course, student=self.student).exists())

        start_response = self.client.post(
            reverse('testing_api:quiz_start', args=[self.quiz.pk]),
            {},
            content_type='application/json',
            **self.auth_headers(self.student),
        )
        self.assertEqual(start_response.status_code, 201)
        attempt_id = start_response.json()['attempt']['id']

        submit_response = self.client.post(
            reverse('testing_api:attempt_submit', args=[attempt_id]),
            {
                'answers': {
                    str(self.question_single.id): [self.single_correct.id],
                    str(self.question_multi.id): [self.multi_correct_1.id, self.multi_correct_2.id],
                }
            },
            content_type='application/json',
            **self.auth_headers(self.student),
        )

        self.assertEqual(submit_response.status_code, 200)
        payload = submit_response.json()
        self.assertEqual(payload['attempt']['score_percent'], 100)
        self.assertEqual(len(payload['answers']), 2)
        self.assertTrue(payload['show_answer_key'])

    def test_api_student_can_save_attempt_draft(self):
        attempt = Attempt.objects.create(quiz=self.quiz, student=self.student)

        response = self.client.post(
            reverse('testing_api:attempt_draft', args=[attempt.pk]),
            json.dumps(
                {
                    'answers': {
                        str(self.question_single.id): [self.single_correct.id],
                        str(self.question_multi.id): [self.multi_correct_1.id],
                    },
                    'last_question_id': self.question_multi.id,
                }
            ),
            content_type='application/json',
            **self.auth_headers(self.student),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['answered_questions_count'], 2)
        self.assertEqual(payload['last_question_id'], self.question_multi.id)

    def test_api_attempt_detail_includes_comparison_data(self):
        self.create_submitted_attempt(student=self.student, answers_mapping=self.partial_answers())
        second_attempt = self.create_submitted_attempt(student=self.student, answers_mapping=self.correct_answers())

        response = self.client.get(
            reverse('testing_api:attempt_detail', args=[second_attempt.pk]),
            **self.auth_headers(self.student),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['comparison']['score_delta'], 60)
        self.assertEqual(payload['comparison']['improved_topics'][0]['topic'], 'ORM')

    def test_api_attempt_detail_hides_answer_key_for_student_when_disabled(self):
        attempt = self.create_submitted_attempt(student=self.student, quiz=self.hidden_quiz)

        response = self.client.get(
            reverse('testing_api:attempt_detail', args=[attempt.pk]),
            **self.auth_headers(self.student),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['show_answer_key'])
        self.assertEqual(payload['answers'][0]['correct_choice_ids'], [])

    def test_api_teacher_can_view_course_analytics(self):
        Enrollment.objects.create(course=self.course, student=self.other_student)
        self.create_submitted_attempt(student=self.student)
        self.create_submitted_attempt(student=self.other_student, answers_mapping=self.partial_answers())

        response = self.client.get(
            reverse('testing_api:course_analytics', args=[self.course.pk]),
            **self.auth_headers(self.teacher),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['course']['id'], self.course.pk)
        self.assertTrue(payload['topic_rows'])
        self.assertTrue(payload['attention_students'])
        self.assertTrue(payload['leaderboard'])

    def test_api_teacher_can_view_quiz_attempts(self):
        self.create_submitted_attempt(student=self.student)

        response = self.client.get(
            reverse('testing_api:quiz_attempts', args=[self.quiz.pk]),
            **self.auth_headers(self.teacher),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['quiz']['id'], self.quiz.pk)
        self.assertEqual(len(payload['attempts']), 1)

    def test_api_student_cannot_open_teacher_analytics(self):
        response = self.client.get(
            reverse('testing_api:course_analytics', args=[self.course.pk]),
            **self.auth_headers(self.student),
        )

        self.assertEqual(response.status_code, 403)

    def test_api_quiz_detail_returns_questions_without_correctness_flags(self):
        response = self.client.get(reverse('testing_api:quiz_detail', args=[self.quiz.pk]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['title'], self.quiz.title)
        self.assertEqual(data['question_count'], 2)
        self.assertEqual(len(data['questions']), 2)
        self.assertNotIn('is_correct', data['questions'][0]['choices'][0])

    def test_schema_and_swagger_pages_are_available(self):
        schema_response = self.client.get(reverse('testing_api:schema'))
        docs_response = self.client.get(reverse('testing_api:docs'))

        self.assertEqual(schema_response.status_code, 200)
        self.assertEqual(docs_response.status_code, 200)
        self.assertIn(b'openapi', schema_response.content.lower())
