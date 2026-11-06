"""Business operations that touch several rows and must stay consistent under concurrency."""
import logging
import re
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext as _

from apps.models import Order, Product, Stream, User, Transaction, SiteSettings

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


def normalize_phone(value):
    """Return the 9 local digits of an Uzbek phone number (the format stored everywhere in the project)."""
    return re.sub(r'\D', '', value or '')[-9:]


@dataclass
class OrderLine:
    product_id: int
    quantity: int
    stream_id: int | None = None


def place_orders(lines, *, full_name, phone_number, region=None, district=None, address='', user=None):
    """
    Create one Order per cart line inside a single transaction.

    Stock is reserved with a conditional UPDATE, so two customers can never buy the last unit twice.
    Prices are snapshotted on the order so later price changes don't rewrite history.
    """
    if not lines:
        raise OrderError(_("Savatingiz bo'sh."))

    created = []
    with transaction.atomic():
        for line in lines:
            if line.quantity < 1:
                raise OrderError(_("Miqdor noto'g'ri."))
            product = Product.objects.filter(pk=line.product_id, is_active=True).first()
            if product is None:
                raise OrderError(_("Mahsulot topilmadi yoki sotuvdan olingan."))

            reserved = Product.objects.filter(pk=product.pk, quantity__gte=line.quantity) \
                .update(quantity=F('quantity') - line.quantity)
            if not reserved:
                raise OrderError(_("«%(name)s» omborda yetarli emas.") % {'name': product.name})

            stream = None
            if line.stream_id:
                stream = Stream.objects.select_related('owner').filter(pk=line.stream_id, product=product).first()

            unit_price = max(product.price - stream.discount, 0) if stream else product.price
            payout = max(product.discount_price - stream.discount, 0) if stream else 0
            created.append(Order.objects.create(
                product=product,
                quantity=line.quantity,
                price=unit_price,
                payout=payout,
                stream=stream,
                referral_user=stream.owner if stream else None,
                full_name=full_name.strip(),
                phone_number=normalize_phone(phone_number),
                region=region,
                district=district,
                address=address or None,
                user=user if user and user.is_authenticated else None,
            ))
    logger.info('Placed %s order(s): %s', len(created), [order.pk for order in created])
    return created


def change_order_status(order_id, new_status, *, actor=None, **changes):
    """
    Move an order to a new status, enforcing Order.TRANSITIONS.

    Side effects are applied exactly once thanks to the row lock:
    - cancelling returns reserved stock to the warehouse;
    - delivering credits the affiliate (stream owner) with the payout.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if new_status != order.status and not order.can_transition_to(new_status):
            raise OrderError(_("Buyurtmani «%(old)s» holatidan «%(new)s» holatiga o'tkazib bo'lmaydi.") % {
                'old': order.get_status_display(), 'new': Order.StatusType(new_status).label})

        for field, value in changes.items():
            setattr(order, field, value)

        if new_status != order.status:
            if new_status in Order.RESTOCK_STATUSES:
                Product.objects.filter(pk=order.product_id).update(quantity=F('quantity') + order.quantity)
            if new_status == Order.StatusType.DELIVERED and not order.is_payout_paid and order.referral_user_id \
                    and order.payout:
                User.objects.filter(pk=order.referral_user_id) \
                    .update(balance=F('balance') + order.payout * order.quantity)
                order.is_payout_paid = True
            if actor is not None and actor.type == User.Type.OPERATOR and order.operator_id is None:
                order.operator = actor
            order.status = new_status
        order.save()
    logger.info('Order #%s -> %s by %s', order.pk, new_status, getattr(actor, 'pk', None))
    return order


def claim_order(order_id, operator):
    """Atomically assign an unclaimed order to an operator. Returns True if this operator owns it afterwards."""
    Order.objects.filter(pk=order_id, operator__isnull=True).update(operator=operator)
    return Order.objects.filter(pk=order_id, operator=operator).exists() or operator.is_superuser


def register_stream_visit(stream_id):
    Stream.objects.filter(pk=stream_id).update(visit_count=F('visit_count') + 1)


class WithdrawalError(Exception):
    pass


def request_withdrawal(user, *, amount, card_number):
    settings = SiteSettings.load()
    if amount < settings.minimum_sum:
        raise WithdrawalError(_("Minimal yechib olish summasi: %(sum)s so'm.") % {'sum': f'{settings.minimum_sum:,}'})
    with transaction.atomic():
        debited = User.objects.filter(pk=user.pk, balance__gte=amount).update(balance=F('balance') - amount)
        if not debited:
            raise WithdrawalError(_("Balansingizda yetarli mablag' mavjud emas."))
        return Transaction.objects.create(user=user, amount=amount, card_number=card_number)
