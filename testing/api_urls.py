from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .api_views import ApiCourseDetailView, ApiCourseListView, ApiQuizDetailView, ApiStatsView

app_name = 'testing_api'

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='testing_api:schema'), name='docs'),
    path('stats/', ApiStatsView.as_view(), name='stats'),
    path('courses/', ApiCourseListView.as_view(), name='course_list'),
    path('courses/<int:pk>/', ApiCourseDetailView.as_view(), name='course_detail'),
    path('quizzes/<int:pk>/', ApiQuizDetailView.as_view(), name='quiz_detail'),
]
