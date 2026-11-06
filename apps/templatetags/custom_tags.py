from decimal import Decimal

from django.template import Library
from django.utils.translation import gettext_lazy as _

register = Library()


@register.filter
def money(value):
    """12345000 → '12 345 000 so'm'."""
    try:
        amount = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return value
    return f"{amount:,}".replace(',', ' ') + " so'm"


@register.filter
def number(value):
    try:
        return f"{int(value or 0):,}".replace(',', ' ')
    except (TypeError, ValueError):
        return value


@register.filter
def phone(value):
    """'901234567' → '+998 (90) 123-45-67'."""
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())[-9:]
    if len(digits) != 9:
        return value or ''
    return f'+998 ({digits[:2]}) {digits[2:5]}-{digits[5:7]}-{digits[7:]}'


@register.filter
def mask_phone(value):
    """Hide the middle of a customer's number for affiliates: '+998 (90) ***-**-67'."""
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())[-9:]
    if len(digits) != 9:
        return '—'
    return f'+998 ({digits[:2]}) ***-**-{digits[7:]}'


@register.filter
def percent_of(value, total):
    try:
        return min(100, round(float(value) * 100 / float(total))) if float(total) else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def stars(rating):
    """Return five booleans for rendering a star row (half and above rounds up)."""
    try:
        filled = int(round(float(rating or 0)))
    except (TypeError, ValueError):
        filled = 0
    return [i < filled for i in range(5)]


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Current query string with some parameters replaced/removed (value None or '' removes it)."""
    query = context['request'].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ''):
            query.pop(key, None)
        else:
            query[key] = value
    if 'page' not in kwargs:
        query.pop('page', None)
    encoded = query.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.filter('custom_date')
def custom_date(value):
    months = {
        1: _('Yanvar'), 2: _('Fevral'), 3: _('Mart'), 4: _('Aprel'), 5: _('May'), 6: _('Iyun'),
        7: _('Iyul'), 8: _('Avgust'), 9: _('Sentabr'), 10: _('Oktabr'), 11: _('Noyabr'), 12: _('Dekabr'),
    }
    if not value:
        return ''
    return f"{value.day} {months.get(value.month, '')} {value.year}"


@register.filter(is_safe=True)
def custom_intcomma(value):
    """Split a card number into groups of four digits: 8600123412341234 → '8600 1234 1234 1234'."""
    try:
        if not isinstance(value, (float, Decimal)):
            value = int(value)
    except (TypeError, ValueError):
        return value
    result = str(value)
    return ' '.join(result[i:i + 4] for i in range(0, len(result), 4))
