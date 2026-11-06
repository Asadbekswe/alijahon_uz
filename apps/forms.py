from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import authenticate, password_validation
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.forms import CharField, CheckboxInput, ChoiceField, ClearableFileInput, Form, IntegerField, \
    ModelChoiceField, ModelForm, PasswordInput, RadioSelect, Select, Textarea, TextInput
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.models import District, Order, Product, Region, Review, Stream, User
from apps.services import normalize_phone


def validate_phone(value):
    phone = normalize_phone(value)
    if len(phone) != 9:
        raise ValidationError(_("Telefon raqamni to'liq kiriting: +998 (XX) XXX-XX-XX"))
    return phone


def validate_full_name(value):
    value = (value or '').strip()
    if len(value) < 3:
        raise ValidationError(_("Ism kamida 3 ta belgidan iborat bo'lishi kerak."))
    if any(ch.isdigit() for ch in value):
        raise ValidationError(_("Ismda raqam bo'lishi mumkin emas."))
    return value


PHONE_FIELDS = {'phone', 'phone_number'}


class StyledFormMixin:
    """Give every widget the storefront design-system classes and sensible input hints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (CheckboxInput, RadioSelect, ClearableFileInput)):
                continue
            css = 'select' if isinstance(widget, Select) else 'textarea' if isinstance(widget, Textarea) else 'input'
            widget.attrs['class'] = f"{css} {widget.attrs.get('class', '')}".strip()
            if name in PHONE_FIELDS:
                widget.attrs.update({'data-phone': '', 'inputmode': 'tel', 'autocomplete': 'tel',
                                     'placeholder': '+998 (__) ___-__-__'})
            if self.is_bound and name in self.errors:
                widget.attrs['aria-invalid'] = 'true'
        if 'region' in self.fields and 'district' in self.fields:
            # Districts are loaded for the chosen region by app.js (see [data-region-select]).
            self.fields['region'].widget.attrs.update({
                'data-region-select': self['district'].id_for_label, 'data-url': reverse('get_districts', args=[0])})
            selected = self['district'].value()
            self.fields['district'].widget.attrs['data-selected'] = selected or ''
            self.fields['region'].empty_label = _('Viloyatni tanlang')
            self.fields['district'].empty_label = _('Tumanni tanlang')


class RateLimitMixin:
    """Locks a phone+IP pair after too many failed attempts (shared via the cache backend)."""

    def _rate_key(self, phone):
        ip = self.request.META.get('REMOTE_ADDR', '') if self.request else ''
        return f'login-fail:{phone}:{ip}'

    def check_rate_limit(self, phone):
        if cache.get(self._rate_key(phone), 0) >= settings.LOGIN_RATE_LIMIT:
            raise ValidationError(_("Juda ko'p urinish. Birozdan so'ng qayta urinib ko'ring."), code='rate_limited')

    def register_failure(self, phone):
        key = self._rate_key(phone)
        cache.add(key, 0, settings.LOGIN_RATE_WINDOW)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, settings.LOGIN_RATE_WINDOW)

    def reset_failures(self, phone):
        cache.delete(self._rate_key(phone))


class CustomAdminAuthenticationForm(RateLimitMixin, AdminAuthenticationForm):

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].widget.attrs["maxlength"] = 25

    def clean_username(self):
        return normalize_phone(self.cleaned_data.get('username'))

    def clean(self):
        phone = self.cleaned_data.get('username')
        if phone:
            self.check_rate_limit(phone)
        try:
            cleaned = super().clean()
        except ValidationError:
            if phone:
                self.register_failure(phone)
            raise
        if phone:
            self.reset_failures(phone)
        return cleaned


class UserAuthenticatedForm(StyledFormMixin, RateLimitMixin, Form):
    phone = CharField(label=_('Telefon raqam'), max_length=25)
    password = CharField(label=_('Parol'), strip=False,
                         widget=PasswordInput(attrs={"autocomplete": "current-password"}))

    error_messages = {
        'invalid_login': _("Telefon raqam yoki parol noto'g'ri."),
        'inactive': _("Bu akkaunt faol emas."),
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        return validate_phone(self.cleaned_data.get('phone'))

    def clean(self):
        phone = self.cleaned_data.get("phone")
        password = self.cleaned_data.get("password")
        if phone and password:
            self.check_rate_limit(phone)
            self.user_cache = authenticate(self.request, phone=phone, password=password)
            if self.user_cache is None:
                self.register_failure(phone)
                raise ValidationError(self.error_messages['invalid_login'], code='invalid_login')
            if not self.user_cache.is_active:
                raise ValidationError(self.error_messages['inactive'], code='inactive')
            self.reset_failures(phone)
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class UserRegisterForm(StyledFormMixin, ModelForm):
    phone = CharField(label=_('Telefon raqam'), max_length=25)
    password1 = CharField(label=_('Parol'), strip=False, widget=PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = CharField(label=_('Parolni tasdiqlang'), strip=False,
                          widget=PasswordInput(attrs={'autocomplete': 'new-password'}))

    class Meta:
        model = User
        fields = 'first_name', 'phone'

    def clean_phone(self):
        phone = validate_phone(self.cleaned_data.get('phone'))
        if User.objects.filter(phone=phone).exists():
            raise ValidationError(_("Bu raqam allaqachon ro'yxatdan o'tgan."))
        return phone

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', _("Parollar mos kelmadi."))
        if p1:
            try:
                password_validation.validate_password(p1, User(phone=cleaned.get('phone') or ''))
            except ValidationError as error:
                self.add_error('password1', error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserSettingsForm(StyledFormMixin, ModelForm):
    region = ModelChoiceField(queryset=Region.objects.all(), required=False)

    class Meta:
        model = User
        fields = 'first_name', 'last_name', 'address', 'telegram_id', 'district'
        widgets = {'address': TextInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.district_id:
            self.fields['region'].initial = self.instance.district.region_id

    def clean(self):
        cleaned = super().clean()
        region, district = cleaned.get('region'), cleaned.get('district')
        if district and region and district.region_id != region.pk:
            self.add_error('district', _("Tuman tanlangan viloyatga tegishli emas."))
        return cleaned


class UserChangePasswordForm(StyledFormMixin, Form):
    password = CharField(label=_('Joriy parol'), strip=False, widget=PasswordInput)
    password1 = CharField(label=_('Yangi parol'), strip=False, widget=PasswordInput)
    password2 = CharField(label=_('Yangi parolni tasdiqlang'), strip=False, widget=PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.user.check_password(password):
            raise ValidationError(_("Joriy parol noto'g'ri."))
        return password

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error('password2', _("Parollar mos kelmadi."))
        elif p1:
            try:
                password_validation.validate_password(p1, self.user)
            except ValidationError as error:
                self.add_error('password1', error)
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data["password1"])
        self.user.save(update_fields=['password'])
        return self.user


class CheckoutForm(StyledFormMixin, Form):
    full_name = CharField(label=_('Ism familiya'), max_length=255)
    phone_number = CharField(label=_('Telefon raqam'), max_length=25)
    region = ModelChoiceField(label=_('Viloyat'), queryset=Region.objects.all())
    district = ModelChoiceField(label=_('Tuman'), queryset=District.objects.all(), required=False)
    address = CharField(label=_('Manzil'), max_length=255, required=False)

    def clean_full_name(self):
        return validate_full_name(self.cleaned_data.get('full_name'))

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data.get('phone_number'))

    def clean(self):
        cleaned = super().clean()
        region, district = cleaned.get('region'), cleaned.get('district')
        if district and region and district.region_id != region.pk:
            self.add_error('district', _("Tuman tanlangan viloyatga tegishli emas."))
        return cleaned


class QuickOrderForm(StyledFormMixin, Form):
    """One-step order straight from a product / stream page (the original Alijahon flow)."""
    product = ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    stream = ModelChoiceField(queryset=Stream.objects.all(), required=False)
    quantity = IntegerField(min_value=1, max_value=99, initial=1)
    full_name = CharField(max_length=255)
    phone_number = CharField(max_length=25)

    def clean_full_name(self):
        return validate_full_name(self.cleaned_data.get('full_name'))

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data.get('phone_number'))


class StreamForm(StyledFormMixin, ModelForm):
    product = ModelChoiceField(queryset=Product.objects.filter(is_active=True))

    class Meta:
        model = Stream
        fields = 'name', 'discount', 'product'

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if len(name) < 3:
            raise ValidationError(_("Oqim nomi kamida 3 ta belgidan iborat bo'lishi kerak."))
        return name

    def clean(self):
        cleaned = super().clean()
        product, discount = cleaned.get('product'), cleaned.get('discount') or 0
        if product and discount > product.discount_price:
            self.add_error('discount', _("Chegirma to'lov miqdoridan (%(max)s so'm) oshmasligi kerak.")
                           % {'max': f'{product.discount_price:,}'.replace(',', ' ')})
        return cleaned


class ReviewForm(StyledFormMixin, ModelForm):
    rating = ChoiceField(choices=[(i, i) for i in range(5, 0, -1)])

    class Meta:
        model = Review
        fields = 'rating', 'text'
        widgets = {'text': Textarea(attrs={'rows': 4})}


class OperatorUpdateForm(StyledFormMixin, ModelForm):
    class Meta:
        model = Order
        fields = 'full_name', 'quantity', 'region', 'district', 'address', 'send_order_date', 'status', \
            'comment_operator'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = {self.instance.status, *self.instance.allowed_transitions()}
        self.fields['status'].choices = [c for c in Order.StatusType.choices if c[0] in allowed]
        self.fields['quantity'].min_value = 1

    def clean(self):
        cleaned = super().clean()
        region, district = cleaned.get('region'), cleaned.get('district')
        if district and region and district.region_id != region.pk:
            self.add_error('district', _("Tuman tanlangan viloyatga tegishli emas."))
        if cleaned.get('status') == Order.StatusType.READY and not region:
            self.add_error('region', _("Yetkazib berish uchun viloyatni tanlang."))
        return cleaned


class OperatorOrderCreateForm(StyledFormMixin, Form):
    product = ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    quantity = IntegerField(min_value=1, max_value=99, initial=1)
    full_name = CharField(max_length=255)
    phone_number = CharField(max_length=25)
    region = ModelChoiceField(queryset=Region.objects.all())
    district = ModelChoiceField(queryset=District.objects.all(), required=False)
    address = CharField(max_length=255, required=False)

    def clean_full_name(self):
        return validate_full_name(self.cleaned_data.get('full_name'))

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data.get('phone_number'))


class TransactionCreateForm(StyledFormMixin, Form):
    card_number = CharField(max_length=25)
    amount = IntegerField(min_value=1)

    def clean_card_number(self):
        card_number = ''.join(ch for ch in self.cleaned_data['card_number'] if ch.isdigit())
        if len(card_number) != 16:
            raise ValidationError(_("Karta raqami 16 ta raqamdan iborat bo'lishi kerak."))
        return card_number


class CourierStatusForm(StyledFormMixin, Form):
    status = ChoiceField(choices=[
        (Order.StatusType.DELIVERED, Order.StatusType.DELIVERED.label),
        (Order.StatusType.BROKEN, Order.StatusType.BROKEN.label),
        (Order.StatusType.CANCELED, Order.StatusType.CANCELED.label),
    ])
    comment = CharField(max_length=255, required=False)
