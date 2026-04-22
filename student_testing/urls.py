from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'Администрирование EduTesting'
admin.site.site_title = 'EduTesting Admin'
admin.site.index_title = 'Управление пользователями, курсами и безопасностью'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('testing.api_urls')),
    path('accounts/', include('accounts.urls')),
    path('', include('testing.urls')),
]
