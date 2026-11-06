from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.context_processors import NAV_CATEGORIES_KEY
from apps.models import Category, Product, Review


@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=Review)
def invalidate_storefront_cache(**kwargs):
    cache.delete_many([NAV_CATEGORIES_KEY, 'home:sections'])
