from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .api_views import (
    ApiAttemptDetailView,
    ApiAttemptAppealReviewView,
    ApiAttemptAppealView,
    ApiAttemptDraftSaveView,
    ApiAttemptSubmitView,
    ApiCourseAnalyticsView,
    ApiCourseDetailView,
    ApiCourseEnrollView,
    ApiCourseIntegrityView,
    ApiCourseListView,
    ApiMeView,
    ApiMyAchievementsView,
    ApiMyCourseListView,
    ApiPasswordChangeView,
    ApiQuizAttemptsView,
    ApiQuizDetailView,
    ApiQuizOverrideListCreateView,
    ApiQuizStartView,
    ApiStatsView,
    ApiTokenAuthView,
)

app_name = 'testing_api'

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path(
        'docs/',
        SpectacularSwaggerView.as_view(
            url_name='testing_api:schema',
            template_name='testing/swagger_ui.html',
        ),
        name='docs',
    ),
    path('auth/token/', ApiTokenAuthView.as_view(), name='token_auth'),
    path('auth/password/change/', ApiPasswordChangeView.as_view(), name='password_change'),
    path('me/', ApiMeView.as_view(), name='me'),
    path('stats/', ApiStatsView.as_view(), name='stats'),
    path('courses/', ApiCourseListView.as_view(), name='course_list'),
    path('my/courses/', ApiMyCourseListView.as_view(), name='my_course_list'),
    path('my/achievements/', ApiMyAchievementsView.as_view(), name='my_achievements'),
    path('courses/<int:pk>/', ApiCourseDetailView.as_view(), name='course_detail'),
    path('courses/<int:pk>/enroll/', ApiCourseEnrollView.as_view(), name='course_enroll'),
    path('courses/<int:pk>/analytics/', ApiCourseAnalyticsView.as_view(), name='course_analytics'),
    path('courses/<int:pk>/integrity/', ApiCourseIntegrityView.as_view(), name='course_integrity'),
    path('quizzes/<int:pk>/', ApiQuizDetailView.as_view(), name='quiz_detail'),
    path('quizzes/<int:pk>/overrides/', ApiQuizOverrideListCreateView.as_view(), name='quiz_overrides'),
    path('quizzes/<int:pk>/start/', ApiQuizStartView.as_view(), name='quiz_start'),
    path('quizzes/<int:pk>/attempts/', ApiQuizAttemptsView.as_view(), name='quiz_attempts'),
    path('attempts/<int:pk>/', ApiAttemptDetailView.as_view(), name='attempt_detail'),
    path('attempts/<int:pk>/appeal/', ApiAttemptAppealView.as_view(), name='attempt_appeal'),
    path('appeals/<int:pk>/review/', ApiAttemptAppealReviewView.as_view(), name='attempt_appeal_review'),
    path('attempts/<int:pk>/draft/', ApiAttemptDraftSaveView.as_view(), name='attempt_draft'),
    path('attempts/<int:pk>/submit/', ApiAttemptSubmitView.as_view(), name='attempt_submit'),
]
