from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve

from apps.admin import admin_site

handler404 = 'apps.views.utils_views.handler404'
handler500 = 'apps.views.utils_views.handler500'


urlpatterns = [
    path('', include('apps.urls')),
    path("ckeditor5/", include('django_ckeditor_5.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    re_path(r'^rosetta/', include('rosetta.urls')),
] + i18n_patterns(
    path('admin/', admin_site.urls),
    prefix_default_language=False,
)

if settings.SERVE_MEDIA:
    urlpatterns += [re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT})]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
if settings.ENABLE_DEBUG_TOOLBAR:
    urlpatterns += [path('__debug__/', include('debug_toolbar.urls'))]
