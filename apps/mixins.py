from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views import View

from apps.models import User


class GetObjectMixins(LoginRequiredMixin, View):

    def get_object(self, queryset=None):
        return self.request.user


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict a view to the given user types. Superusers always pass."""
    allowed_types = ()

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.type in self.allowed_types


class OperatorRequiredMixin(RoleRequiredMixin):
    allowed_types = (User.Type.OPERATOR, User.Type.MANAGER, User.Type.ADMIN)


class CurrierRequiredMixin(RoleRequiredMixin):
    allowed_types = (User.Type.CURRIER, User.Type.MANAGER, User.Type.ADMIN)


def switch_lang_code(path, language):
    lang_codes = [c for (c, name) in settings.LANGUAGES]

    if path == '':
        raise Exception('URL path for language switch is empty')
    elif path[0] != '/':
        raise Exception('URL path for language switch does not start with "/"')
    elif language not in lang_codes:
        raise Exception('%s is not a supported language code' % language)

    parts = path.split('/')

    if parts[1] in lang_codes:
        parts[1] = language
    else:
        parts[0] = "/" + language

    return '/'.join(parts)
