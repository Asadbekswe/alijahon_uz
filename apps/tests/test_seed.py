import pytest
from django.core.management import call_command

from apps.models import Category, Order, Product, Review, User


@pytest.mark.django_db
def test_seed_is_idempotent(settings, monkeypatch):
    settings.DEBUG = True
    for key in ('SEED_ADMIN_PASSWORD', 'SEED_CUSTOMER_PASSWORD', 'SEED_STAFF_PASSWORD'):
        monkeypatch.setenv(key, 'Test-pass-2026')
    call_command('seed_dev_data', '--skip-images')
    counts = (Product.objects.count(), Category.objects.count(), Order.objects.count(), Review.objects.count(),
              User.objects.count())
    call_command('seed_dev_data', '--skip-images')
    assert counts == (Product.objects.count(), Category.objects.count(), Order.objects.count(),
                      Review.objects.count(), User.objects.count())
    assert counts[0] >= 30
    assert User.objects.get(phone='900000002').check_password('Test-pass-2026')


@pytest.mark.django_db
def test_seed_refuses_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(Exception):
        call_command('seed_dev_data')
