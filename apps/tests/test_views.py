import pytest
from django.urls import reverse

from apps.models import Favorite, Order, Review, Stream, User

pytestmark = pytest.mark.django_db

PUBLIC_PAGES = ['main_base', 'category_list', 'cart_page', 'login_page', 'register_page']


@pytest.mark.parametrize('name', PUBLIC_PAGES)
def test_public_pages_render(client, product, name):
    assert client.get(reverse(name)).status_code == 200


def test_product_and_stream_pages(client, product, stream):
    assert client.get(product.get_absolute_url()).status_code == 200
    response = client.get(stream.get_absolute_url())
    assert response.status_code == 200
    assert response.context['price'] == 970_000
    client.get(stream.get_absolute_url())  # same session: counted once
    stream.refresh_from_db()
    assert stream.visit_count == 1


def test_catalog_filters_and_search(client, product):
    url = reverse('category_list')
    assert client.get(url, {'q': 'Smart'}).context['paginator'].count == 1
    assert client.get(url, {'min_price': 2_000_000}).context['paginator'].count == 0
    assert client.get(url, {'on_sale': 1, 'sort': 'price_desc'}).context['paginator'].count == 1
    assert client.get(reverse('search'), {'q': 'smart'}).json()['results'][0]['name'] == 'Smartfon X'


def test_cart_to_checkout_creates_orders(client, product, region, site_settings):
    response = client.post(reverse('cart_add'), {'product': product.pk, 'quantity': 2},
                           HTTP_ACCEPT='application/json')
    assert response.json()['count'] == 2
    response = client.post(reverse('checkout_page'), {
        'full_name': 'Ali Valiyev', 'phone_number': '+998 (90) 123-45-67', 'region': region.pk,
        'district': region.districts.first().pk, 'address': '12-uy'})
    assert response.status_code == 302 and response.url == reverse('success_order_view')
    order = Order.objects.get()
    assert (order.quantity, order.phone_number, order.region) == (2, '901234567', region)
    assert client.get(reverse('success_order_view')).status_code == 200
    assert client.get(reverse('cart_page')).context['cart'].items == []


def test_checkout_validates_phone_and_name(client, product, region):
    client.post(reverse('cart_add'), {'product': product.pk})
    response = client.post(reverse('checkout_page'), {'full_name': 'A1', 'phone_number': '123', 'region': region.pk})
    assert response.status_code == 200
    assert set(response.context['form'].errors) == {'full_name', 'phone_number'}
    assert not Order.objects.exists()


def test_cart_quantity_is_capped_by_stock(client, product):
    client.post(reverse('cart_add'), {'product': product.pk, 'quantity': 50})
    assert client.get(reverse('cart_page')).context['cart'].items[0].quantity == 5


def test_quick_order_from_stream(client, stream):
    response = client.post(reverse('success_order_page'), {
        'product': stream.product_id, 'stream': stream.pk, 'quantity': 1, 'full_name': 'Ali Valiyev',
        'phone_number': '901234567'})
    assert response.status_code == 302
    assert Order.objects.get().referral_user == stream.owner


def test_login_does_not_auto_register(client):
    response = client.post(reverse('login_page'), {'phone': '901234567', 'password': 'whatever-123'})
    assert response.status_code == 200
    assert not User.objects.filter(phone='901234567').exists()


def test_login_rate_limit(client, customer, settings):
    settings.LOGIN_RATE_LIMIT = 2
    for _ in range(2):
        client.post(reverse('login_page'), {'phone': customer.phone, 'password': 'bad'})
    response = client.post(reverse('login_page'), {'phone': customer.phone, 'password': 'Str0ng-pass-123'})
    assert response.status_code == 200 and '_auth_user_id' not in client.session


def test_register_and_login(client):
    response = client.post(reverse('register_page'), {
        'first_name': 'Vali', 'phone': '+998 (93) 555-44-33', 'password1': 'Kuchli-parol-77',
        'password2': 'Kuchli-parol-77'})
    assert response.status_code == 302
    assert User.objects.get(phone='935554433').check_password('Kuchli-parol-77')
    client.post(reverse('logaut_page'))
    response = client.post(reverse('login_page'), {'phone': '935554433', 'password': 'Kuchli-parol-77'})
    assert response.status_code == 302


def test_logout_requires_post(client, customer):
    client.force_login(customer)
    client.get(reverse('logaut_page'))
    assert '_auth_user_id' in client.session


@pytest.mark.parametrize('name', ['operator_page', 'operator_add_order', 'currier_page'])
def test_staff_pages_forbidden_for_customers(client, customer, name):
    client.force_login(customer)
    assert client.get(reverse(name)).status_code == 403


def test_staff_pages_require_login(client):
    assert client.get(reverse('operator_page')).status_code == 302


def test_operator_flow(client, operator, product, region):
    order = Order.objects.create(product=product, full_name='Ali', phone_number='901234567', price=product.price)
    client.force_login(operator)
    assert client.get(reverse('operator_page')).status_code == 200
    response = client.post(reverse('operator_detail', args=[order.pk]), {
        'full_name': 'Ali Valiyev', 'quantity': 1, 'region': region.pk, 'district': '', 'address': '',
        'send_order_date': '', 'status': Order.StatusType.READY, 'comment_operator': ''})
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == Order.StatusType.READY and order.operator == operator


def test_courier_takes_and_delivers(client, courier, product, stream, affiliate):
    order = Order.objects.create(product=product, stream=stream, referral_user=affiliate, full_name='Ali',
                                 phone_number='901234567', price=970_000, payout=70_000,
                                 status=Order.StatusType.READY)
    client.force_login(courier)
    client.post(reverse('currier_take', args=[order.pk]))
    client.post(reverse('currier_detail_page', args=[order.pk]), {'status': 'delivered'})
    order.refresh_from_db()
    affiliate.refresh_from_db()
    assert order.status == Order.StatusType.DELIVERED and order.currier == courier
    assert affiliate.balance == 70_000


def test_stream_owner_is_forced_to_request_user(client, customer, affiliate, product):
    client.force_login(customer)
    client.post(reverse('create_stream_page'),
                {'name': 'Telegram', 'discount': 0, 'product': product.pk, 'owner': affiliate.pk})
    assert Stream.objects.get().owner == customer


def test_stream_discount_cannot_exceed_payout(client, customer, product):
    client.force_login(customer)
    client.post(reverse('create_stream_page'), {'name': 'Telegram', 'discount': 500_000, 'product': product.pk})
    assert not Stream.objects.exists()


def test_inquiries_only_show_own_stream_orders(client, customer, stream, product):
    Order.objects.create(product=product, stream=stream, full_name='X', phone_number='901234567')
    client.force_login(customer)
    assert list(client.get(reverse('inquiries_page')).context['orders']) == []


def test_order_detail_is_private(client, customer, affiliate, product):
    order = Order.objects.create(product=product, user=affiliate, full_name='X', phone_number='901234567')
    client.force_login(customer)
    assert client.get(reverse('order_detail', args=[order.pk])).status_code == 404


def test_favorite_toggle_is_post_only(client, customer, product):
    client.force_login(customer)
    client.get(reverse('add_favourite_page', args=[product.pk]))
    assert not Favorite.objects.exists()
    response = client.post(reverse('add_favourite_page', args=[product.pk]), HTTP_ACCEPT='application/json')
    assert response.json()['liked'] is True


def test_review_create_and_update(client, customer, product):
    client.force_login(customer)
    url = reverse('product_review', args=[product.slug])
    client.post(url, {'rating': 4, 'text': 'Yaxshi'})
    client.post(url, {'rating': 5, 'text': "A'lo"})
    assert Review.objects.get().rating == 5


def test_withdrawal_view(client, customer, site_settings):
    User.objects.filter(pk=customer.pk).update(balance=100_000)
    client.force_login(customer)
    response = client.post(reverse('payment_page'), {'card_number': '8600 1234 1234 1234', 'amount': 60_000})
    assert response.status_code == 302
    customer.refresh_from_db()
    assert customer.balance == 40_000


def test_partner_and_account_pages_render(client, customer, product, stream, site_settings):
    client.force_login(customer)
    for name in ['profile_page', 'settings_page', 'order_page', 'favorite_page', 'market_page', 'steam_page',
                 'statistika_page', 'inquiries_page', 'diagrams_page', 'competition_page', 'payment_page']:
        assert client.get(reverse(name)).status_code == 200, name


def test_admin_dashboard(client, product, site_settings):
    admin = User.objects.create_superuser(phone='900000009', password='Admin-pass-77')
    client.force_login(admin)
    assert client.get(reverse('admin:index')).status_code == 200


def test_healthcheck(client, db):
    assert client.get('/healthz/').json() == {'status': 'ok'}
