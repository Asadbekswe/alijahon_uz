from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import UpdateView, ListView, FormView, TemplateView

from apps.forms import UserAuthenticatedForm, UserSettingsForm, UserChangePasswordForm, OperatorUpdateForm, \
    OperatorOrderCreateForm, UserRegisterForm, CourierStatusForm
from apps.mixins import GetObjectMixins, OperatorRequiredMixin, CurrierRequiredMixin
from apps.models import User, Region, Order, SiteSettings, Favorite, Stream
from apps.services import OrderError, OrderLine, change_order_status, claim_order, place_orders


def safe_next(request, fallback):
    candidate = request.POST.get('next') or request.GET.get('next')
    if candidate and url_has_allowed_host_and_scheme(candidate, {request.get_host()}, request.is_secure()):
        return candidate
    return fallback


def home_for(user):
    if user.type == User.Type.OPERATOR:
        return reverse('operator_page')
    if user.type == User.Type.CURRIER:
        return reverse('currier_page')
    return reverse('main_base')


class UserLoginView(LoginView):
    template_name = 'apps/auth/login.html'
    redirect_authenticated_user = True
    form_class = UserAuthenticatedForm

    def form_valid(self, form):
        login(self.request, form.get_user())
        messages.success(self.request, _("Xush kelibsiz!"))
        return redirect(safe_next(self.request, home_for(form.get_user())))


class UserRegisterView(FormView):
    template_name = 'apps/auth/register.html'
    form_class = UserRegisterForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('main_base')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(self.request, _("Akkaunt yaratildi. Xaridlaringiz muborak!"))
        return redirect(safe_next(self.request, reverse('main_base')))


class UserLogautView(View):
    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect('main_base')

    def get(self, request, *args, **kwargs):
        # Logging out via GET is CSRF-able; show a confirmation instead.
        if not request.user.is_authenticated:
            return redirect('main_base')
        return redirect(f"{reverse('profile_page')}?logout=1")


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'apps/auth/profile.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        orders = Order.objects.filter(user=user)
        ctx['order_count'] = orders.count()
        ctx['active_order_count'] = orders.filter(
            status__in=[Order.StatusType.NEW, Order.StatusType.READY, Order.StatusType.DELIVERING]).count()
        ctx['favorite_count'] = Favorite.objects.filter(user=user).count()
        ctx['stream_count'] = Stream.objects.filter(owner=user).count()
        ctx['recent_orders'] = orders.select_related('product')[:4]
        ctx['confirm_logout'] = self.request.GET.get('logout') == '1'
        return ctx


class UserSettingsView(GetObjectMixins, UpdateView):
    template_name = 'apps/auth/settings.html'
    success_url = reverse_lazy('settings_page')
    form_class = UserSettingsForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['regions'] = Region.objects.all()
        context['password_form'] = kwargs.get('password_form') or UserChangePasswordForm(self.request.user)
        return context

    def form_valid(self, form):
        messages.success(self.request, _("Ma'lumotlar saqlandi."))
        return super().form_valid(form)


class UserChangeImageView(GetObjectMixins, UpdateView):
    template_name = 'apps/auth/settings.html'
    success_url = reverse_lazy('settings_page')
    fields = 'image',

    def form_valid(self, form):
        messages.success(self.request, _("Rasm yangilandi."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, form.errors.get('image', [_("Rasmni yuklab bo'lmadi.")])[0])
        return redirect('settings_page')

    def get(self, request, *args, **kwargs):
        return redirect('settings_page')


class UserChangePasswordView(LoginRequiredMixin, View):
    def post(self, request):
        form = UserChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, _("Parol yangilandi."))
            return redirect('settings_page')
        view = UserSettingsView()
        view.setup(request)
        view.object = request.user
        return view.render_to_response(view.get_context_data(form=UserSettingsForm(instance=request.user),
                                                             password_form=form))

    def get(self, request):
        return redirect('settings_page')


# ----------------------------------------------------------------------------------------------- operators

OPERATOR_TABS = [
    Order.StatusType.NEW, Order.StatusType.READY, Order.StatusType.DELIVERING, Order.StatusType.DELIVERED,
    Order.StatusType.CANT_PHONE, Order.StatusType.BROKEN, Order.StatusType.CANCELED, Order.StatusType.ARCHIVED,
]


def operator_scope(user):
    qs = Order.objects.all()
    if user.is_superuser or user.type in (User.Type.ADMIN, User.Type.MANAGER):
        return qs
    return qs.filter(Q(operator=user) | Q(operator__isnull=True))


class OperatorTabsMixin:
    """Status tabs with live counts for the operator sidebar."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = operator_scope(self.request.user).aggregate(
            **{status.value: Count('pk', filter=Q(status=status)) for status in OPERATOR_TABS})
        context['tabs'] = [(status.value, status.label, counts[status.value]) for status in OPERATOR_TABS]
        context.setdefault('active_status', None)
        return context


class OperatorOrderListView(OperatorRequiredMixin, OperatorTabsMixin, ListView):
    template_name = 'apps/operators/operator_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_status(self):
        status = self.kwargs.get('status') or Order.StatusType.NEW
        if status not in Order.StatusType.values:
            raise Http404
        return status

    def get_queryset(self):
        qs = operator_scope(self.request.user).filter(status=self.get_status()) \
            .select_related('product', 'stream', 'region', 'district', 'operator', 'referral_user')
        search = self.request.GET.get('q', '').strip()
        if search:
            digits = ''.join(ch for ch in search if ch.isdigit())
            condition = Q(full_name__icontains=search)
            if digits:
                condition |= Q(phone_number__contains=digits) | Q(pk=int(digits[:18]))
            qs = qs.filter(condition)
        return qs.order_by('-created_at')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, active_status=self.get_status(), **kwargs)
        context['search'] = self.request.GET.get('q', '')
        return context


class OperatorClaimView(OperatorRequiredMixin, View):
    def post(self, request, pk):
        if claim_order(pk, request.user):
            return redirect('operator_detail', pk=pk)
        messages.error(request, _("Bu buyurtmani boshqa operator allaqachon qabul qilgan."))
        return redirect('operator_page')


class OperatorDetailView(OperatorRequiredMixin, OperatorTabsMixin, UpdateView):
    template_name = 'apps/operators/operator_detail.html'
    context_object_name = 'order'
    form_class = OperatorUpdateForm

    def get_queryset(self):
        return operator_scope(self.request.user).select_related(
            'product', 'stream', 'region', 'district', 'operator', 'referral_user')

    def get_object(self, queryset=None):
        order = super().get_object(queryset)
        if order.operator_id is None:
            claim_order(order.pk, self.request.user)
            order.refresh_from_db()
        return order

    def get_context_data(self, **kwargs):
        context = super().get_context_data(active_status=self.object.status, **kwargs)
        context['site_settings'] = SiteSettings.load()
        context['delivery_fee'] = context['site_settings'].delivery_price_for(self.object.region)
        context['previous_orders'] = Order.objects.filter(phone_number=self.object.phone_number) \
            .exclude(pk=self.object.pk).select_related('product')[:5]
        return context

    def form_valid(self, form):
        data = form.cleaned_data
        changes = {field: data[field] for field in form.changed_data if field != 'status'}
        try:
            change_order_status(self.object.pk, data['status'], actor=self.request.user, **changes)
        except OrderError as error:
            form.add_error('status', str(error))
            return self.form_invalid(form)
        messages.success(self.request, _("Buyurtma #%(id)s saqlandi.") % {'id': self.object.pk})
        return redirect('operator_status_page', status=data['status'])


class OperatorCreateOrderView(OperatorRequiredMixin, OperatorTabsMixin, FormView):
    template_name = 'apps/operators/operator_add_product.html'
    form_class = OperatorOrderCreateForm

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            orders = place_orders([OrderLine(product_id=data['product'].pk, quantity=data['quantity'])],
                                  full_name=data['full_name'], phone_number=data['phone_number'],
                                  region=data['region'], district=data.get('district'), address=data.get('address'))
        except OrderError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        Order.objects.filter(pk__in=[o.pk for o in orders]).update(operator=self.request.user)
        messages.success(self.request, _("Buyurtma yaratildi."))
        return redirect('operator_page')


# ----------------------------------------------------------------------------------------------- couriers

COURIER_TABS = [
    ('pool', _('Yangi'), Q(status=Order.StatusType.READY, currier__isnull=True)),
    ('delivering', _('Yetkazilmoqda'), Q(status=Order.StatusType.DELIVERING)),
    ('delivered', _('Yetkazildi'), Q(status=Order.StatusType.DELIVERED)),
    ('returned', _('Qaytarildi'), Q(status__in=[Order.StatusType.BROKEN, Order.StatusType.CANCELED])),
]


def courier_scope(user, tab):
    condition = dict((key, cond) for key, _label, cond in COURIER_TABS)[tab]
    qs = Order.objects.filter(condition)
    if tab != 'pool' and not (user.is_superuser or user.type in (User.Type.ADMIN, User.Type.MANAGER)):
        qs = qs.filter(currier=user)
    return qs


class CurrierListView(CurrierRequiredMixin, ListView):
    template_name = 'apps/couriers/currier_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_tab(self):
        tab = self.request.GET.get('tab', 'pool')
        return tab if tab in {key for key, _l, _c in COURIER_TABS} else 'pool'

    def get_queryset(self):
        qs = courier_scope(self.request.user, self.get_tab()) \
            .select_related('product', 'region', 'district').order_by('send_order_date', '-created_at')
        region = self.request.GET.get('region')
        if region and region.isdigit():
            qs = qs.filter(region_id=region)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['tabs'] = [(key, label, courier_scope(user, key).count()) for key, label, _c in COURIER_TABS]
        ctx['active_tab'] = self.get_tab()
        ctx['regions'] = Region.objects.all()
        ctx['active_region'] = self.request.GET.get('region', '')
        ctx['delivered_sum'] = courier_scope(user, 'delivered').aggregate(
            s=Sum('price'))['s'] or 0
        ctx['status_form'] = CourierStatusForm()
        return ctx


class CurrierOrderListView(CurrierRequiredMixin, View):
    """Legacy URL: the courier list now has tabs."""

    def get(self, request):
        return redirect(f"{reverse('currier_page')}?tab=delivering")


class CurrierTakeOrderView(CurrierRequiredMixin, View):
    def post(self, request, pk):
        taken = Order.objects.filter(pk=pk, status=Order.StatusType.READY, currier__isnull=True) \
            .update(currier=request.user)
        if not taken:
            messages.error(request, _("Bu buyurtmani boshqa kuryer olgan."))
            return redirect('currier_page')
        change_order_status(pk, Order.StatusType.DELIVERING, actor=request.user)
        messages.success(request, _("Buyurtma #%(id)s sizga biriktirildi.") % {'id': pk})
        return redirect(f"{reverse('currier_page')}?tab=delivering")


class CurrierOrderDetailView(CurrierRequiredMixin, View):
    """Courier reports the delivery outcome."""

    def post(self, request, pk):
        order = get_object_or_404(courier_scope(request.user, 'delivering'), pk=pk)
        form = CourierStatusForm(request.POST)
        if form.is_valid():
            changes = {'comment_operator': form.cleaned_data['comment']} if form.cleaned_data['comment'] else {}
            try:
                change_order_status(order.pk, form.cleaned_data['status'], actor=request.user, **changes)
                messages.success(request, _("Buyurtma #%(id)s yangilandi.") % {'id': order.pk})
            except OrderError as error:
                messages.error(request, str(error))
        return redirect(f"{reverse('currier_page')}?tab=delivering")

    def get(self, request, pk=None):
        return redirect('currier_page')
