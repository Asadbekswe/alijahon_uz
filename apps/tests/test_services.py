import pytest

from apps.models import Order, Product, User, Transaction
from apps.services import OrderError, OrderLine, WithdrawalError, change_order_status, claim_order, place_orders, \
    request_withdrawal
from apps.tests.conftest import image_file
from apps.models import Category

pytestmark = pytest.mark.django_db


def order_for(product, **kwargs):
    return place_orders([OrderLine(product.pk, kwargs.pop('quantity', 1), kwargs.pop('stream_id', None))],
                        full_name='Ali Valiyev', phone_number='+998 (90) 111-22-33', **kwargs)[0]


def test_place_order_reserves_stock_and_snapshots_price(product):
    order = order_for(product, quantity=2)
    product.refresh_from_db()
    assert product.quantity == 3
    assert order.price == 1_000_000 and order.total == 2_000_000
    assert order.phone_number == '901112233'
    assert order.status == Order.StatusType.NEW


def test_place_order_rejects_more_than_stock_and_rolls_back(product, category):
    other = Product.objects.create(name='Y', description='d', image=image_file(), price=10, quantity=1,
                                   category=category)
    with pytest.raises(OrderError):
        place_orders([OrderLine(product.pk, 1), OrderLine(other.pk, 2)], full_name='Ali', phone_number='901112233')
    product.refresh_from_db()
    assert product.quantity == 5  # first line rolled back together with the failing one
    assert not Order.objects.exists()


def test_stream_order_applies_discount_and_payout(product, stream):
    order = order_for(product, stream_id=stream.pk)
    assert order.price == 970_000
    assert order.payout == 70_000
    assert order.referral_user == stream.owner


def test_invalid_transition_is_rejected(product):
    order = order_for(product)
    with pytest.raises(OrderError):
        change_order_status(order.pk, Order.StatusType.DELIVERED)


def test_delivery_credits_affiliate_exactly_once(product, stream, affiliate):
    order = order_for(product, stream_id=stream.pk, quantity=2)
    for status in (Order.StatusType.READY, Order.StatusType.DELIVERING, Order.StatusType.DELIVERED):
        change_order_status(order.pk, status)
    affiliate.refresh_from_db()
    assert affiliate.balance == 140_000
    change_order_status(order.pk, Order.StatusType.DELIVERED)  # same status again: no double credit
    affiliate.refresh_from_db()
    assert affiliate.balance == 140_000


def test_cancel_restocks(product):
    order = order_for(product, quantity=3)
    change_order_status(order.pk, Order.StatusType.CANCELED)
    product.refresh_from_db()
    assert product.quantity == 5


def test_claim_is_exclusive(product, operator):
    order = order_for(product)
    other = User.objects.create_user(phone='909999999', password='x', type=User.Type.OPERATOR)
    assert claim_order(order.pk, operator) is True
    assert claim_order(order.pk, other) is False


def test_withdrawal_checks_minimum_and_balance(customer, site_settings):
    User.objects.filter(pk=customer.pk).update(balance=100_000)
    with pytest.raises(WithdrawalError):
        request_withdrawal(customer, amount=10_000, card_number='8600123412341234')
    with pytest.raises(WithdrawalError):
        request_withdrawal(customer, amount=200_000, card_number='8600123412341234')
    request_withdrawal(customer, amount=60_000, card_number='8600123412341234')
    customer.refresh_from_db()
    assert customer.balance == 40_000
    assert Transaction.objects.get(user=customer).amount == 60_000


def test_slug_is_stable_and_unique(category):
    a = Product.objects.create(name='Same', description='d', image=image_file(), price=1, category=category)
    b = Product.objects.create(name='Same', description='d', image=image_file(), price=1, category=category)
    assert a.slug != b.slug
    a.name = 'Renamed'
    a.save()
    a.refresh_from_db()
    assert a.slug == 'same'
    assert Category.objects.get(pk=category.pk).slug == 'elektronika'
