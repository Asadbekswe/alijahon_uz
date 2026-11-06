from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils.functional import SimpleLazyObject

from apps.cart import Cart
from apps.models import Category, Favorite

NAV_CATEGORIES_KEY = 'nav:categories'


def nav_categories():
    categories = cache.get(NAV_CATEGORIES_KEY)
    if categories is None:
        categories = list(Category.objects.annotate(
            product_count=Count('products', filter=Q(products__is_active=True))
        ).order_by('position', 'name'))
        cache.set(NAV_CATEGORIES_KEY, categories, 600)
    return categories


def storefront(request):
    """Data every storefront page needs. Everything is lazy, so pages that don't use it pay nothing."""
    user = getattr(request, 'user', None)

    def favorite_ids():
        if user is None or not user.is_authenticated:
            return set()
        return set(Favorite.objects.filter(user=user).values_list('product_id', flat=True))

    def cart_count():
        return len(Cart(request.session)) if hasattr(request, 'session') else 0

    return {
        'nav_categories': SimpleLazyObject(nav_categories),
        'favorite_ids': SimpleLazyObject(favorite_ids),
        'cart_count': SimpleLazyObject(cart_count),
        'support_phone': settings.STORE_SUPPORT_PHONE,
    }
