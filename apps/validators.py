from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _


def validate_image_size(file):
    limit = settings.MAX_IMAGE_UPLOAD_SIZE
    if file and getattr(file, 'size', 0) > limit:
        raise ValidationError(_('Image is too large (max %(limit)s).'), params={'limit': filesizeformat(limit)})
