from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView, CreateView, TemplateView, DetailView, FormView

from apps.cart import Cart
from apps.forms import CheckoutForm, QuickOrderForm, StreamForm
from apps.models import Order, SiteSettings, Product, Stream, Favorite, Competition, User
from apps.services import OrderError, OrderLine, place_orders

LAST_ORDERS_KEY = 'last_orders'


def wants_json(request):
    return 'application/json' in request.headers.get('Accept', '')


def cart_payload(cart, **extra):
    return {'count': len(cart), 'subtotal': cart.subtotal, 'savings': cart.savings, **extra}


def parse_quantity(value, default=1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class CartView(TemplateView):
    template_name = 'apps/cart/cart.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cart = Cart(self.request.session)
        ctx['cart'] = cart
        ctx['suggestions'] = Product.objects.for_cards().filter(quantity__gt=0) \
            .exclude(pk__in=[item.product.pk for item in cart.items]).order_by('-sold_count')[:4]
        return ctx


class CartAddView(View):
    def post(self, request):
        product = get_object_or_404(Product.objects.active(), pk=request.POST.get('product'))
        cart = Cart(request.session)
        quantity = max(parse_quantity(request.POST.get('quantity')), 1)
        if not product.in_stock:
            message = _("Afsuski, bu mahsulot hozir omborda yo'q.")
            if wants_json(request):
                return JsonResponse(cart_payload(cart, ok=False, message=message), status=409)
            messages.error(request, message)
            return redirect(product.get_absolute_url())
        line_qty = cart.add(product, quantity, stream_id=request.POST.get('stream') or None)
        message = _("«%(name)s» savatga qo'shildi.") % {'name': product.name}
        if wants_json(request):
            return JsonResponse(cart_payload(cart, ok=True, message=message, line_quantity=line_qty))
        messages.success(request, message)
        return redirect(request.POST.get('next') or 'cart_page')


class CartUpdateView(View):
    def post(self, request):
        cart = Cart(request.session)
        key = request.POST.get('key', '')
        if request.POST.get('action') == 'remove':
            cart.remove(key)
            quantity = 0
        else:
            quantity = cart.set_quantity(key, parse_quantity(request.POST.get('quantity'), 0))
        if wants_json(request):
            item = next((i for i in cart.items if i.key == key), None)
            return JsonResponse(cart_payload(cart, ok=True, key=key, quantity=quantity,
                                             line_total=item.total if item else 0))
        return redirect('cart_page')


class CheckoutView(FormView):
    template_name = 'apps/cart/checkout.html'
    form_class = CheckoutForm

    def dispatch(self, request, *args, **kwargs):
        self.cart = Cart(request.session)
        if not self.cart.items:
            messages.info(request, _("Savatingiz bo'sh — avval mahsulot tanlang."))
            return redirect('cart_page')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        user = self.request.user
        if not user.is_authenticated:
            return {}
        return {
            'full_name': user.get_full_name(),
            'phone_number': user.phone,
            'region': user.district.region_id if user.district_id else None,
            'district': user.district_id,
            'address': user.address,
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        settings = SiteSettings.load()
        form = ctx['form']
        region = form.cleaned_data.get('region') if form.is_bound and hasattr(form, 'cleaned_data') else None
        ctx.update({
            'cart': self.cart,
            'site_settings': settings,
            'delivery_fee': settings.delivery_price_for(region),
            'delivery_tariffs': {
                'tashkent': int(settings.delivery_price_tashkent),
                'tashkent_region': int(settings.delivery_price_tashkent_region),
                'regions': int(settings.delivery_price_regions),
            },
        })
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            orders = place_orders(self.cart.as_order_lines(), full_name=data['full_name'],
                                  phone_number=data['phone_number'], region=data['region'],
                                  district=data.get('district'), address=data.get('address', ''),
                                  user=self.request.user)
        except OrderError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        self.cart.clear()
        self.request.session[LAST_ORDERS_KEY] = [order.pk for order in orders]
        return redirect('success_order_view')


class CreatedSuccessOrderedView(View):
    """POST target of the one-step order form on product and stream pages (kept for existing links)."""

    def post(self, request):
        form = QuickOrderForm(request.POST)
        product_url = reverse('main_base')
        if form.data.get('stream'):
            product_url = reverse('stream_detail', args=[form.data['stream']])
        elif form.data.get('product'):
            product = Product.objects.filter(pk=form.data.get('product')).first()
            product_url = product.get_absolute_url() if product else product_url
        if not form.is_valid():
            for errors in form.errors.values():
                messages.error(request, errors[0])
            return redirect(product_url)
        data = form.cleaned_data
        stream = data.get('stream')
        line = OrderLine(product_id=data['product'].pk, quantity=data['quantity'],
                         stream_id=stream.pk if stream else None)
        try:
            orders = place_orders([line], full_name=data['full_name'], phone_number=data['phone_number'],
                                  user=request.user)
        except OrderError as error:
            messages.error(request, str(error))
            return redirect(product_url)
        request.session[LAST_ORDERS_KEY] = [order.pk for order in orders]
        return redirect('success_order_view')

    def get(self, request):
        return redirect('success_order_view')


class OrderSuccessView(TemplateView):
    template_name = 'apps/orders/success_ordered.html'

    def get(self, request, *args, **kwargs):
        if not request.session.get(LAST_ORDERS_KEY):
            return redirect('main_base')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        orders = list(Order.objects.filter(pk__in=self.request.session.get(LAST_ORDERS_KEY, []))
                      .select_related('product', 'region', 'district').order_by('pk'))
        ctx['orders'] = orders
        ctx['order'] = orders[0] if orders else None
        ctx['total'] = sum(order.total for order in orders)
        return ctx


class OrderListView(LoginRequiredMixin, ListView):
    template_name = 'apps/orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        qs = Order.objects.filter(user=self.request.user).select_related('product', 'region')
        status = self.request.GET.get('status')
        if status in Order.StatusType.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Order.StatusType.choices
        ctx['active_status'] = self.request.GET.get('status', '')
        ctx['querystring'] = f"status={ctx['active_status']}" if ctx['active_status'] in Order.StatusType.values else ''
        return ctx


class OrderDetailView(LoginRequiredMixin, DetailView):
    template_name = 'apps/orders/order_detail.html'
    context_object_name = 'order'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).select_related('product', 'region', 'district', 'stream')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        steps = [Order.StatusType.NEW, Order.StatusType.READY, Order.StatusType.DELIVERING,
                 Order.StatusType.DELIVERED]
        status = self.object.status
        current = steps.index(status) if status in steps else -1
        ctx['steps'] = [{'label': step.label, 'done': i <= current, 'current': i == current}
                        for i, step in enumerate(steps)]
        ctx['is_terminated'] = status in (Order.StatusType.CANCELED, Order.StatusType.BROKEN,
                                          Order.StatusType.ARCHIVED, Order.StatusType.CANT_PHONE)
        return ctx


class StreamCreateView(LoginRequiredMixin, CreateView):
    template_name = 'apps/market.html'
    form_class = StreamForm
    success_url = reverse_lazy('steam_page')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, _("Oqim yaratildi. Havolani nusxalab, reklamada ulashing."))
        return super().form_valid(form)

    def form_invalid(self, form):
        for errors in form.errors.values():
            messages.error(self.request, errors[0])
        return redirect(self.request.META.get('HTTP_REFERER') or 'market_page')

    def get(self, request, *args, **kwargs):
        return redirect('market_page')


class StreamListView(LoginRequiredMixin, ListView):
    template_name = 'apps/orders/stream_list.html'
    context_object_name = 'streams'
    paginate_by = 12

    def get_queryset(self):
        return Stream.objects.filter(owner=self.request.user).select_related('product') \
            .annotate(order_total=Count('orders'),
                      delivered=Count('orders', filter=Q(orders__status=Order.StatusType.DELIVERED))).order_by('-pk')


class StreamDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        stream = get_object_or_404(Stream, pk=pk, owner=request.user)
        stream.delete()
        messages.success(request, _("Oqim o'chirildi."))
        return redirect('steam_page')


class FavouriteListView(LoginRequiredMixin, ListView):
    template_name = 'apps/products/favorite.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.for_cards().filter(favorites__user=self.request.user) \
            .order_by('-favorites__created_at')


class FavoriteView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        obj, created = Favorite.objects.get_or_create(user=request.user, product=product)
        if not created:
            obj.delete()
        if wants_json(request):
            return JsonResponse({'ok': True, 'liked': created,
                                 'count': Favorite.objects.filter(user=request.user).count()})
        return redirect(request.POST.get('next') or product.get_absolute_url())

    def get(self, request, pk, *args, **kwargs):
        # State changes are POST only; old GET links just land on the product.
        product = get_object_or_404(Product, pk=pk)
        return redirect(product.get_absolute_url())


class CompetitionListView(LoginRequiredMixin, ListView):
    template_name = 'apps/statistics/competition.html'
    context_object_name = 'users'
    paginate_by = 50

    def get_competition(self):
        if not hasattr(self, '_competition'):
            self._competition = Competition.objects.filter(is_active=True).order_by('-start_date').first()
        return self._competition

    def get_queryset(self):
        competition = self.get_competition()
        if not competition:
            return User.objects.none()
        delivered = Q(streams__orders__status=Order.StatusType.DELIVERED)
        if competition.start_date:
            delivered &= Q(streams__orders__created_at__date__gte=competition.start_date)
        if competition.end_date:
            delivered &= Q(streams__orders__created_at__date__lte=competition.end_date)
        return User.objects.exclude(type=User.Type.ADMIN) \
            .annotate(order_product_count=Sum('streams__orders__quantity', filter=delivered)) \
            .filter(order_product_count__gt=0).order_by('-order_product_count', 'pk')

    def get_context_data(self, *, object_list=None, **kwargs):
        ctx = super().get_context_data(object_list=object_list, **kwargs)
        ctx['competition'] = self.get_competition()
        return ctx


STATUS_COLUMNS = [
    ('new', Order.StatusType.NEW), ('ready', Order.StatusType.READY), ('deliver', Order.StatusType.DELIVERING),
    ('delivered', Order.StatusType.DELIVERED), ('cant_phone', Order.StatusType.CANT_PHONE),
    ('broken', Order.StatusType.BROKEN), ('canceled', Order.StatusType.CANCELED),
    ('archived', Order.StatusType.ARCHIVED),
]


class StatisticView(LoginRequiredMixin, ListView):
    template_name = 'apps/statistics/statistic.html'
    context_object_name = 'streams'
    PERIODS = [('today', 'Bugun'), ('yesterday', 'Kecha'), ('weekly', 'Shu hafta'), ('monthly', 'Shu oy'),
               ('all', 'Hammasi')]

    def get_period_range(self):
        today = timezone.localdate()
        period = self.request.GET.get('period', 'all')
        return {
            'today': (today, None),
            'yesterday': (today - timedelta(days=1), today),
            'weekly': (today - timedelta(days=today.weekday()), None),
            'monthly': (today.replace(day=1), None),
        }.get(period, (None, None))

    def get_queryset(self):
        start, end = self.get_period_range()
        period_filter = Q()
        if start:
            period_filter &= Q(orders__created_at__date__gte=start)
        if end:
            period_filter &= Q(orders__created_at__date__lt=end)
        annotations = {name: Count('orders', filter=period_filter & Q(orders__status=status))
                       for name, status in STATUS_COLUMNS}
        return Stream.objects.filter(owner=self.request.user).select_related('product') \
            .annotate(**annotations).order_by('-pk')

    def get_context_data(self, *, object_list=None, **kwargs):
        ctx = super().get_context_data(object_list=object_list, **kwargs)
        streams = ctx['streams']
        ctx['totals'] = {name: sum(getattr(s, name) for s in streams) for name, _status in STATUS_COLUMNS}
        ctx['totals']['visits'] = sum(s.visit_count for s in streams)
        ctx['columns'] = [(name, status.label) for name, status in STATUS_COLUMNS]
        ctx['periods'] = [(key, _(label)) for key, label in self.PERIODS]
        ctx['active_period'] = self.request.GET.get('period', 'all')
        return ctx
