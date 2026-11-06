from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AppsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps'
    verbose_name = _('Buyurtmalar')

    def ready(self):
        from apps import signals  # noqa: F401
