from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin, StackedInline, TabularInline
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.admin.apps_admin import site_register
from apps.models import Category, Product, ProductImage, Review, User, SiteSettings, Favorite, Competition, Order, \
    District, Region, Transaction, Operator, Stream
from apps.models.proxy.proxy import UserProxyModel, UserOperatorProxyModel, UserManagerProxyModel, \
    UserAdminProxyModel, UserCurrierProxyModel
from apps.services import OrderError, change_order_status


def thumbnail(image, size=40):
    if image:
        return format_html('<img src="{}" width="{}" height="{}" style="object-fit:cover;border-radius:8px" alt="">',
                           image.url, size, size)
    return '—'


class OperatorStackedInline(StackedInline):
    model = Operator
    extra = 0
    max_num = 1


@site_register(User)
class UserModelAdmin(UserAdmin):
    list_display = 'phone', 'full_name', 'type', 'balance', 'is_active', 'date_joined'
    list_filter = 'type', 'is_active', 'is_staff'
    inlines = [OperatorStackedInline]
    ordering = '-date_joined',
    search_fields = "phone", "first_name", "last_name"
    readonly_fields = 'last_login', 'date_joined'
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        (_('Shaxsiy'), {"fields": ("first_name", "last_name", "image", "address", "district", "telegram_id")}),
        (_('Rol va balans'), {"fields": ("type", "balance")}),
        (_('Ruxsatlar'), {"classes": ("collapse",),
                          "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_('Sanalar'), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "type", "password1", "password2")}),
    )

    @admin.display(description=_('Ism'))
    def full_name(self, obj):
        return obj.get_full_name() or '—'


@site_register(Category)
class CategoryModelAdmin(ModelAdmin):
    list_display = 'show_image', 'name', 'position', 'product_count'
    list_display_links = 'show_image', 'name'
    list_editable = 'position',
    search_fields = 'name',

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).annotate(_products=Count('products'))

    @admin.display(description=_('Mahsulotlar'), ordering='_products')
    def product_count(self, obj):
        return obj._products

    @admin.display(description=_('Rasm'))
    def show_image(self, obj):
        return thumbnail(obj.image)


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = 'preview', 'image', 'position'
    readonly_fields = 'preview',

    @admin.display(description='')
    def preview(self, obj):
        return thumbnail(obj.image, 56)


@site_register(Product)
class ProductModelAdmin(ModelAdmin):
    list_display = 'show_image', 'name', 'category', 'price', 'old_price', 'discount_price', 'stock',  'is_active', \
        'is_featured'
    list_display_links = 'show_image', 'name'
    list_editable = 'price', 'is_active', 'is_featured'
    list_filter = 'is_active', 'is_featured', 'category'
    list_select_related = 'category',
    search_fields = 'name', 'short_description'
    readonly_fields = 'slug', 'created_at', 'updated_at'
    inlines = [ProductImageInline]
    actions = 'activate', 'deactivate'
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'category', 'short_description', 'description', 'image')}),
        (_('Narx va ombor'), {'fields': ('price', 'old_price', 'discount_price', 'quantity')}),
        (_("Ko'rinish"), {'fields': ('is_active', 'is_featured', 'specifications')}),
        (_('Sanalar'), {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description=_('Rasm'))
    def show_image(self, obj):
        return thumbnail(obj.image)

    @admin.display(description=_('Ombor'), ordering='quantity')
    def stock(self, obj):
        color = '#b42318' if obj.quantity == 0 else '#b54708' if obj.quantity <= 5 else '#067647'
        return format_html('<b style="color:{}">{}</b>', color, obj.quantity)

    @admin.action(description=_('Faollashtirish'))
    def activate(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description=_("Sotuvdan olish"))
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)


@site_register(Review)
class ReviewModelAdmin(ModelAdmin):
    list_display = 'product', 'user', 'rating', 'short_text', 'is_published', 'created_at'
    list_filter = 'is_published', 'rating'
    list_editable = 'is_published',
    list_select_related = 'product', 'user'
    search_fields = 'text', 'product__name', 'user__phone'
    autocomplete_fields = 'product', 'user'

    @admin.display(description=_('Matn'))
    def short_text(self, obj):
        return (obj.text[:80] + '…') if len(obj.text) > 80 else obj.text


@site_register(Order)
class OrderModelAdmin(ModelAdmin):
    list_display = 'id', 'full_name', 'phone', 'product', 'quantity', 'total_display', 'status', 'region', \
        'operator', 'created_at'
    list_filter = 'status', 'region', 'created_at'
    list_select_related = 'product', 'region', 'operator'
    search_fields = 'id', 'full_name', 'phone_number', 'product__name'
    date_hierarchy = 'created_at'
    readonly_fields = 'price', 'payout', 'is_payout_paid', 'created_at', 'updated_at'
    raw_id_fields = 'product', 'stream', 'user', 'referral_user'
    list_per_page = 50
    actions = 'mark_ready', 'mark_canceled'

    @admin.display(description=_('Telefon'))
    def phone(self, obj):
        return f'+998 {obj.phone_number}'

    @admin.display(description=_('Jami'))
    def total_display(self, obj):
        return f"{obj.total:,} so'm".replace(',', ' ')

    def save_model(self, request, obj, form, change):
        # Route status changes through the service so stock and payouts stay consistent.
        if change and 'status' in form.changed_data:
            new_status = obj.status
            obj.status = form.initial['status']
            super().save_model(request, obj, form, change)
            try:
                change_order_status(obj.pk, new_status, actor=request.user)
            except OrderError as error:
                self.message_user(request, str(error), messages.ERROR)
            return
        super().save_model(request, obj, form, change)

    def _bulk(self, request, queryset, status):
        done = 0
        for pk in queryset.values_list('pk', flat=True):
            try:
                change_order_status(pk, status, actor=request.user)
                done += 1
            except OrderError:
                pass
        self.message_user(request, _('%(done)s ta buyurtma yangilandi.') % {'done': done})

    @admin.action(description=_("Yetkazishga tayyor"))
    def mark_ready(self, request, queryset):
        self._bulk(request, queryset, Order.StatusType.READY)

    @admin.action(description=_("Bekor qilish"))
    def mark_canceled(self, request, queryset):
        self._bulk(request, queryset, Order.StatusType.CANCELED)


@site_register(Stream)
class StreamModelAdmin(ModelAdmin):
    list_display = 'name', 'owner', 'product', 'discount', 'visit_count', 'created_at'
    list_select_related = 'owner', 'product'
    search_fields = 'name', 'owner__phone', 'product__name'
    raw_id_fields = 'owner', 'product'


@site_register(Region)
class ReginModelAdmin(ModelAdmin):
    list_display = 'name',
    search_fields = 'name',


@site_register(District)
class DistrictModelAdmin(ModelAdmin):
    list_display = 'name', 'region'
    list_filter = 'region',
    list_select_related = 'region',
    search_fields = 'name',


@site_register(SiteSettings)
class SiteSettingsModelAdmin(ModelAdmin):
    list_display = '__str__', 'delivery_price_tashkent', 'delivery_price_tashkent_region', 'delivery_price_regions', \
        'minimum_sum'

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()


@site_register(Favorite)
class FavouriteModelAdmin(ModelAdmin):
    list_display = 'user', 'product', 'created_at'
    list_select_related = 'user', 'product'
    raw_id_fields = 'user', 'product'


@site_register(Transaction)
class TransactionModelAdmin(ModelAdmin):
    list_display = 'user', 'amount', 'masked_card', 'status', 'created_at'
    list_filter = 'status',
    list_editable = 'status',
    list_select_related = 'user',
    search_fields = 'user__phone', 'card_number'
    raw_id_fields = 'user',


@site_register(Competition)
class CompetitionModelAdmin(ModelAdmin):
    list_display = 'id', 'start_date', 'end_date', 'is_active'
    list_editable = 'is_active',


# PROXY USER

@site_register(UserProxyModel)
class UserProxyModelAdmin(UserModelAdmin):
    pass


@site_register(UserOperatorProxyModel)
class UserOperatorProxyModelAdmin(UserModelAdmin):
    pass


@site_register(UserManagerProxyModel)
class UserManagerProxyModelAdmin(UserModelAdmin):
    pass


@site_register(UserAdminProxyModel)
class UserAdminProxyModelAdmin(UserModelAdmin):
    pass


@site_register(UserCurrierProxyModel)
class UserCurrierProxyModelAdmin(UserModelAdmin):
    pass
