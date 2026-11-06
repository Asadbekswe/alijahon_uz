from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Avg, Count, OuterRef, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models import TextChoices, IntegerField, CharField, SET_NULL, FloatField, Model, ImageField, \
    PositiveIntegerField, ForeignKey, CASCADE, BooleanField, DateField, PositiveSmallIntegerField, TextField, \
    JSONField, Index, UniqueConstraint
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.fields import CKEditor5Field

from apps.models.base import SlugBasedModel, TimeBasedModel, SlugTimeBasedModel
from apps.validators import validate_image_size
from .user import User


class Category(SlugBasedModel):
    image = ImageField(upload_to='categories/%Y/%m/%d', verbose_name=_("Category image"),
                       validators=[validate_image_size])
    description = CharField(max_length=255, blank=True, default='', verbose_name=_("short description"))
    position = PositiveSmallIntegerField(default=0, verbose_name=_("position"))

    class Meta:
        ordering = 'position', 'name'
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')

    def get_absolute_url(self):
        return reverse('category_by_slug', args=[self.slug])


class ProductQuerySet(QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_stats(self):
        """Rating and sales figures via correlated subqueries (no row multiplication, no N+1)."""
        reviews = Review.objects.filter(product=OuterRef('pk'), is_published=True).order_by().values('product')
        sold = Order.objects.filter(product=OuterRef('pk')) \
            .exclude(status__in=[Order.StatusType.CANCELED, Order.StatusType.BROKEN]) \
            .order_by().values('product')
        return self.annotate(
            rating_avg=Subquery(reviews.annotate(v=Avg('rating')).values('v')[:1]),
            rating_count=Coalesce(Subquery(reviews.annotate(v=Count('pk')).values('v')[:1]), Value(0)),
            sold_count=Coalesce(Subquery(sold.annotate(v=Sum('quantity')).values('v')[:1]), Value(0)),
        )

    def for_cards(self):
        return self.active().select_related('category').with_stats()


class Product(SlugTimeBasedModel):
    short_description = CharField(max_length=255, blank=True, default='', verbose_name=_("short description"))
    description = CKEditor5Field('Text', config_name='extends')
    image = ImageField(upload_to='products/%Y/%m/%d/', verbose_name=_("image"), validators=[validate_image_size])
    price = PositiveIntegerField(db_default=0, verbose_name=_("price"))
    old_price = PositiveIntegerField(null=True, blank=True, verbose_name=_("price before discount"),
                                     help_text=_("Shown crossed out next to the price. Leave empty if not on sale."))
    quantity = PositiveIntegerField(db_default=0, verbose_name=_("quantity in stock"))
    # Historically named "discount_price": this is the payout ("To'lov") an affiliate earns per delivered unit.
    discount_price = PositiveIntegerField(db_default=0, verbose_name=_("affiliate payout"))
    specifications = JSONField(default=dict, blank=True, verbose_name=_("specifications"))
    is_active = BooleanField(default=True, verbose_name=_("is active"))
    is_featured = BooleanField(default=False, verbose_name=_("is featured"))
    category = ForeignKey('apps.Category', CASCADE, related_name='products')

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = '-created_at',
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        indexes = [
            Index(fields=['is_active', 'category', '-created_at'], name='product_active_cat_idx'),
            Index(fields=['is_active', 'price'], name='product_active_price_idx'),
        ]

    def get_absolute_url(self):
        return reverse('product_detail', args=[self.slug])

    @property
    def in_stock(self):
        return self.quantity > 0

    @property
    def is_low_stock(self):
        return 0 < self.quantity <= 5

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return round((self.old_price - self.price) * 100 / self.old_price)
        return 0


class ProductImage(Model):
    product = ForeignKey('apps.Product', CASCADE, related_name='images')
    image = ImageField(upload_to='products/gallery/%Y/%m/%d/', validators=[validate_image_size])
    position = PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = 'position', 'id'
        verbose_name = _('Product image')
        verbose_name_plural = _('Product images')


class Review(TimeBasedModel):
    product = ForeignKey('apps.Product', CASCADE, related_name='reviews')
    user = ForeignKey('apps.User', CASCADE, related_name='reviews')
    rating = PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = TextField(max_length=2000, blank=True, default='')
    is_published = BooleanField(default=True)

    class Meta:
        ordering = '-created_at',
        verbose_name = _('Review')
        verbose_name_plural = _('Reviews')
        constraints = [UniqueConstraint(fields=['product', 'user'], name='one_review_per_user_product')]

    def __str__(self):
        return f'{self.product} — {self.rating}★'


class Stream(TimeBasedModel):
    name = CharField(max_length=255, verbose_name=_("stream"))
    visit_count = PositiveIntegerField(db_default=0, verbose_name=_("visit_count"))
    discount = PositiveIntegerField(db_default=0, verbose_name=_("discount"))
    product = ForeignKey('apps.Product', CASCADE, related_name='streams')
    owner = ForeignKey('apps.User', CASCADE, related_name='streams')

    class Meta:
        ordering = '-id',

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('stream_detail', args=[self.pk])

    @property
    def sale_price(self):
        return max(self.product.price - self.discount, 0)

    @property
    def payout(self):
        return max(self.product.discount_price - self.discount, 0)


class Order(TimeBasedModel):
    class StatusType(TextChoices):
        NEW = 'new', _('Yangi')
        READY = "ready", _("Yetkazishga tayyor")
        DELIVERING = "delivering", _("Yetkazilmoqda")
        DELIVERED = "delivered", _("Yetkazildi")
        CANT_PHONE = "cant_phone", _("Telefon ko'tarmadi")
        BROKEN = "broken", _("Nosoz")
        CANCELED = "canceled", _("Bekor qilindi")
        ARCHIVED = "archived", _("Arxivlangan")

    # Allowed status changes. Anything not listed here is rejected by apps.services.change_order_status.
    TRANSITIONS = {
        StatusType.NEW: {StatusType.READY, StatusType.CANT_PHONE, StatusType.CANCELED, StatusType.ARCHIVED},
        StatusType.CANT_PHONE: {StatusType.NEW, StatusType.READY, StatusType.CANCELED, StatusType.ARCHIVED},
        StatusType.READY: {StatusType.DELIVERING, StatusType.CANCELED},
        StatusType.DELIVERING: {StatusType.DELIVERED, StatusType.BROKEN, StatusType.CANCELED},
        StatusType.DELIVERED: set(),
        StatusType.BROKEN: {StatusType.ARCHIVED},
        StatusType.CANCELED: {StatusType.ARCHIVED},
        StatusType.ARCHIVED: set(),
    }
    # Statuses in which the reserved stock goes back to the warehouse.
    RESTOCK_STATUSES = {StatusType.CANCELED}

    quantity = IntegerField(db_default=1, validators=[MinValueValidator(1)], verbose_name=_("quantity"))
    status = CharField(max_length=50, choices=StatusType.choices, default=StatusType.NEW, verbose_name=_("status"))
    full_name = CharField(max_length=255, verbose_name=_("full name"))
    phone_number = CharField(max_length=20, verbose_name=_("phone number"))
    price = PositiveIntegerField(default=0, verbose_name=_("unit price"))
    payout = PositiveIntegerField(default=0, verbose_name=_("affiliate payout per unit"))
    is_payout_paid = BooleanField(default=False, verbose_name=_("payout credited"))
    stream = ForeignKey('apps.Stream', SET_NULL, null=True, blank=True, related_name='orders', verbose_name=_('stream'))
    region = ForeignKey('apps.Region', SET_NULL, null=True, blank=True, related_name='orders', verbose_name=_('region'))
    district = ForeignKey('apps.District', SET_NULL, null=True, blank=True, related_name='orders',
                          verbose_name=_('district'))
    product = ForeignKey('apps.Product', CASCADE, related_name='orders', verbose_name=_('product'))
    user = ForeignKey('apps.User', SET_NULL, null=True, blank=True, related_name='orders')
    operator = ForeignKey('apps.User', SET_NULL, null=True, blank=True, verbose_name=_('operator'),
                          related_name='operator_order', limit_choices_to={'type': User.Type.OPERATOR})
    currier = ForeignKey('apps.User', SET_NULL, null=True, blank=True, verbose_name=_('currier'),
                         related_name='currier_order', limit_choices_to={'type': User.Type.CURRIER})
    referral_user = ForeignKey('apps.User', SET_NULL, null=True, blank=True, related_name='referral_user')
    send_order_date = DateField(null=True, blank=True, verbose_name=_("send order date"))
    address = CharField(max_length=255, null=True, blank=True, verbose_name=_("address for order"))
    comment_operator = CharField(max_length=255, null=True, blank=True,
                                 verbose_name=_("the operator's comment for the order"))

    class Meta:
        ordering = '-created_at',
        verbose_name = _('Order')
        verbose_name_plural = _('Orders')
        indexes = [
            Index(fields=['status', '-created_at'], name='order_status_created_idx'),
            Index(fields=['user', '-created_at'], name='order_user_created_idx'),
        ]

    def __str__(self):
        return f'#{self.pk} {self.get_status_display()}'

    @property
    def total(self):
        return self.price * self.quantity

    def can_transition_to(self, status):
        return status in self.TRANSITIONS.get(self.status, set())

    def allowed_transitions(self):
        return [choice for choice in self.StatusType if choice in self.TRANSITIONS.get(self.status, set())]


class Favorite(TimeBasedModel):
    user = ForeignKey('apps.User', CASCADE, related_name='likes')
    product = ForeignKey('apps.Product', CASCADE, related_name='favorites')

    class Meta:
        verbose_name = _('Like')
        verbose_name_plural = _('Likes')
        unique_together = ('user', 'product')

    def __str__(self):
        return f'{self.user} ♥ {self.product}'


class Competition(TimeBasedModel):
    title = CKEditor5Field('text', config_name='extends')
    description = CKEditor5Field('text', config_name='extends')
    image = ImageField(upload_to='competition/%Y/%m/%d', verbose_name=_("Competition image"),
                       validators=[validate_image_size])
    start_date = DateField(null=True, blank=True, verbose_name=_("Competition start time"))
    end_date = DateField(null=True, blank=True, verbose_name=_("Competition end time"))
    is_active = BooleanField(db_default=False, verbose_name=_("Active competitions"))

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = _('Competition')
        verbose_name_plural = _('Competitions')


class Transaction(TimeBasedModel):
    class Status(TextChoices):
        PROCESS = 'process', _('Ko\'rib chiqilmoqda')
        CANCELED = 'canceled', _('Bekor qilindi')
        PAID = 'paid', _('To\'langan')
        ERROR = 'error', _('Xatolik')

    user = ForeignKey('apps.User', SET_NULL, null=True, related_name='transactions')
    status = CharField(max_length=10, choices=Status.choices, default=Status.PROCESS,
                       verbose_name=_("Transaction status"))
    card_number = CharField(max_length=19, verbose_name=_("Transaction card for user"))
    amount = PositiveIntegerField(db_default=0, verbose_name=_("Transaction amount"))
    text = CharField(max_length=255, null=True, blank=True, verbose_name=_("Transaction description"))
    check_image = ImageField(upload_to='transaction/%Y/%m/%d', null=True, blank=True,
                             verbose_name=_("Transaction image check"), validators=[validate_image_size])

    class Meta:
        ordering = '-created_at',
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")

    def __str__(self):
        return f'{self.user} — {self.amount}'

    @property
    def masked_card(self):
        digits = self.card_number.replace(' ', '')
        return f'•••• {digits[-4:]}' if len(digits) >= 4 else digits


class SiteSettings(Model):
    operator_sum = PositiveIntegerField(db_default=0, verbose_name=_('Operators price'))
    delivery_price_regions = FloatField(db_default=0, verbose_name=_("delivery price for regions"))
    delivery_price_tashkent_region = FloatField(db_default=0, verbose_name=_("delivery price for tashkent regions"))
    delivery_price_tashkent = FloatField(db_default=0, verbose_name=_("delivery price for tashkent"))
    minimum_sum = IntegerField(db_default=1000, verbose_name=_('Minimum transaction sum'))
    operator_repression = IntegerField(db_default=0, verbose_name=_('Operators repression sum'))

    class Meta:
        verbose_name = _('Site Setting')
        verbose_name_plural = _('Site Settings')

    def __str__(self):
        return str(_('Site Settings'))

    @classmethod
    def load(cls):
        """The single settings row; created with database defaults on first use."""
        instance = cls.objects.order_by('pk').first()
        if instance is None:
            instance = cls.objects.create()
            instance.refresh_from_db()
        return instance

    def delivery_price_for(self, region):
        """Delivery fee for a region; Tashkent city and Tashkent region have their own tariffs."""
        if region is None:
            return 0
        name = region.name.lower()
        if 'toshkent shahri' in name or 'tashkent city' in name:
            return int(self.delivery_price_tashkent)
        if 'toshkent' in name or 'tashkent' in name:
            return int(self.delivery_price_tashkent_region)
        return int(self.delivery_price_regions)
