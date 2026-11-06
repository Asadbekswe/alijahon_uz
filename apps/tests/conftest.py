import io

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.models import Category, District, Product, Region, SiteSettings, Stream, User


@pytest.fixture(autouse=True)
def _isolate(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.ALLOWED_HOSTS = ['testserver']
    settings.STORAGES = {**settings.STORAGES, 'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    cache.clear()


def image_file(name='p.png'):
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), '#ff5a1f').save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@pytest.fixture
def region(db):
    region = Region.objects.create(name='Toshkent shahri')
    District.objects.create(name='Yunusobod', region=region)
    return region


@pytest.fixture
def site_settings(db):
    return SiteSettings.objects.create(delivery_price_tashkent=20000, delivery_price_tashkent_region=30000,
                                       delivery_price_regions=40000, minimum_sum=50000)


@pytest.fixture
def category(db):
    return Category.objects.create(name='Elektronika', image=image_file())


@pytest.fixture
def product(category):
    return Product.objects.create(name='Smartfon X', description='<p>desc</p>', image=image_file(), price=1_000_000,
                                  old_price=1_200_000, discount_price=100_000, quantity=5, category=category)


@pytest.fixture
def customer(db):
    return User.objects.create_user(phone='901112233', password='Str0ng-pass-123', first_name='Ali')


@pytest.fixture
def affiliate(db):
    return User.objects.create_user(phone='901112244', password='Str0ng-pass-123')


@pytest.fixture
def operator(db):
    return User.objects.create_user(phone='901112255', password='Str0ng-pass-123', type=User.Type.OPERATOR)


@pytest.fixture
def courier(db):
    return User.objects.create_user(phone='901112266', password='Str0ng-pass-123', type=User.Type.CURRIER)


@pytest.fixture
def stream(product, affiliate):
    return Stream.objects.create(name='Instagram', product=product, owner=affiliate, discount=30_000)
