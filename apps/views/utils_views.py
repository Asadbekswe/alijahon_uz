from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum, F
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView, FormView

from apps.forms import TransactionCreateForm
from apps.models import Product, District, Order, SiteSettings, Stream
from apps.models.shop import Transaction
from apps.services import WithdrawalError, request_withdrawal


class InquiriesView(LoginRequiredMixin, ListView):
    """Orders that came through the current affiliate's streams."""
    template_name = 'apps/orders/inquiries.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.filter(stream__owner=self.request.user) \
            .select_related('product', 'stream', 'region').order_by('-created_at')
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


class CoinsView(LoginRequiredMixin, View):
    """The coins programme was never implemented; the leaderboard lives on the competition page."""

    def get(self, request):
        return redirect('competition_page')


class TransactionCreateView(LoginRequiredMixin, FormView):
    template_name = 'apps/payment.html'
    form_class = TransactionCreateForm

    def form_valid(self, form):
        try:
            request_withdrawal(self.request.user, amount=form.cleaned_data['amount'],
                               card_number=form.cleaned_data['card_number'])
        except WithdrawalError as error:
            form.add_error('amount', str(error))
            return self.form_invalid(form)
        messages.success(self.request, "So'rov qabul qilindi. Mablag' 24 soat ichida kartangizga o'tkaziladi.")
        return redirect('payment_page')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        user.refresh_from_db(fields=['balance'])
        transactions = Transaction.objects.filter(user=user)
        ctx['transactions'] = transactions[:20]
        ctx['site_settings'] = SiteSettings.load()
        ctx['paid_total'] = transactions.filter(status=Transaction.Status.PAID).aggregate(s=Sum('amount'))['s'] or 0
        ctx['pending_total'] = transactions.filter(status=Transaction.Status.PROCESS) \
            .aggregate(s=Sum('amount'))['s'] or 0
        ctx['expected_total'] = Order.objects.filter(
            referral_user=user, is_payout_paid=False,
            status__in=[Order.StatusType.NEW, Order.StatusType.READY, Order.StatusType.DELIVERING],
        ).aggregate(s=Sum(F('payout') * F('quantity')))['s'] or 0
        return ctx


class DiagramView(LoginRequiredMixin, TemplateView):
    template_name = 'apps/statistics/diagram.html'
    DAYS = 30

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        start = today - timedelta(days=self.DAYS - 1)
        orders = Order.objects.filter(stream__owner=user, created_at__date__gte=start)
        daily = {row['day']: row for row in orders.annotate(day=TruncDate('created_at')).values('day').annotate(
            total=Count('pk'), delivered=Count('pk', filter=Q(status=Order.StatusType.DELIVERED)))}
        days = [start + timedelta(days=i) for i in range(self.DAYS)]
        by_status = {row['status']: row['n'] for row in orders.values('status').annotate(n=Count('pk'))}
        top_streams = Stream.objects.filter(owner=user).annotate(
            n=Count('orders', filter=Q(orders__created_at__date__gte=start))).filter(n__gt=0).order_by('-n')[:6]
        chart = {
            'labels': [d.strftime('%d.%m') for d in days],
            'orders': [daily.get(d, {}).get('total', 0) for d in days],
            'delivered': [daily.get(d, {}).get('delivered', 0) for d in days],
            'statuses': [{'label': s.label, 'value': by_status.get(s.value, 0), 'key': s.value}
                         for s in Order.StatusType if by_status.get(s.value)],
            'streams': [{'label': s.name, 'value': s.n} for s in top_streams],
        }
        ctx['chart'] = chart
        ctx['total_orders'] = sum(chart['orders'])
        ctx['total_delivered'] = sum(chart['delivered'])
        ctx['conversion'] = round(ctx['total_delivered'] * 100 / ctx['total_orders']) if ctx['total_orders'] else 0
        ctx['visits'] = Stream.objects.filter(owner=user).aggregate(v=Sum('visit_count'))['v'] or 0
        ctx['days'] = self.DAYS
        return ctx


class DistrictListView(View):
    def get(self, request, region_id):
        districts = District.objects.filter(region_id=region_id).values('id', 'name')
        return JsonResponse(list(districts), safe=False)


class HeaderSearchView(View):
    LIMIT = 6

    def get(self, request, *args, **kwargs):
        search = request.GET.get('search', request.GET.get('q', '')).strip()[:100]
        if len(search) < 2:
            return JsonResponse({'results': [], 'query': search})
        products = Product.objects.active().select_related('category') \
            .filter(Q(name__icontains=search) | Q(category__name__icontains=search)) \
            .only('name', 'slug', 'price', 'old_price', 'image', 'category__name')[:self.LIMIT]
        results = [{
            'name': product.name,
            'url': product.get_absolute_url(),
            'price': product.price,
            'old_price': product.old_price if product.discount_percent else None,
            'image': product.image.url if product.image else '',
            'category': product.category.name,
        } for product in products]
        return JsonResponse({'results': results, 'query': search})


def handler404(request, exception=None, *args, **kwargs):
    return render(request, '404.html', status=404)


def handler500(request, *args, **kwargs):
    return render(request, '500.html', status=500)
