from datetime import timedelta

from django.contrib.admin import AdminSite
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.forms import CustomAdminAuthenticationForm

REVENUE_STATUSES = ('new', 'ready', 'delivering', 'delivered')


class MyAdminSite(AdminSite):
    site_header = _("Alijahon Admin Paneli")
    site_title = _("Alijahon Administratsiyasi")
    index_title = _("Boshqaruv paneli")
    login_form = CustomAdminAuthenticationForm
    index_template = 'admin/dashboard.html'

    def dashboard_context(self):
        from apps.models import Order, Product, Review, User, Transaction

        today = timezone.localdate()
        start = today - timedelta(days=29)
        prev_start = start - timedelta(days=30)
        orders = Order.objects.all()
        current = orders.filter(created_at__date__gte=start)
        previous = orders.filter(created_at__date__gte=prev_start, created_at__date__lt=start)

        def totals(qs):
            return qs.aggregate(
                count=Count('pk'),
                revenue=Sum(F('price') * F('quantity'), filter=Q(status='delivered')),
                pipeline=Sum(F('price') * F('quantity'), filter=Q(status__in=REVENUE_STATUSES)),
            )

        cur, prev = totals(current), totals(previous)

        def delta(key):
            a, b = cur[key] or 0, prev[key] or 0
            return round((a - b) * 100 / b) if b else None

        daily = {row['day']: row for row in current.annotate(day=TruncDate('created_at')).values('day').annotate(
            n=Count('pk'), revenue=Sum(F('price') * F('quantity'), filter=Q(status='delivered')))}
        days = [start + timedelta(days=i) for i in range(30)]
        status_counts = {row['status']: row['n'] for row in orders.values('status').annotate(n=Count('pk'))}

        chart = {
            'labels': [d.strftime('%d.%m') for d in days],
            'orders': [daily.get(d, {}).get('n', 0) for d in days],
            'revenue': [daily.get(d, {}).get('revenue') or 0 for d in days],
            'statuses': [{'key': s.value, 'label': str(s.label), 'value': status_counts.get(s.value, 0)}
                         for s in Order.StatusType],
        }
        return {
            'kpis': [
                {'label': _('Daromad (30 kun)'), 'value': cur['revenue'] or 0, 'suffix': "so'm",
                 'delta': delta('revenue'), 'hint': _('yetkazilgan buyurtmalar')},
                {'label': _('Buyurtmalar (30 kun)'), 'value': cur['count'], 'delta': delta('count'),
                 'hint': _('barcha holatlar')},
                {'label': _('Kutilayotgan tushum'), 'value': cur['pipeline'] or 0, 'suffix': "so'm",
                 'delta': delta('pipeline'), 'hint': _('yangi → yetkazilmoqda')},
                {'label': _('Mijozlar'), 'value': User.objects.filter(type=User.Type.USER).count(),
                 'hint': _("jami ro'yxatdan o'tgan")},
            ],
            'chart': chart,
            'status_counts': chart['statuses'],
            'top_products': Product.objects.annotate(
                n=Sum('orders__quantity', filter=Q(orders__created_at__date__gte=start)
                      & ~Q(orders__status__in=['canceled', 'broken']))).filter(n__gt=0).order_by('-n')[:6],
            'low_stock': Product.objects.filter(is_active=True, quantity__lte=5).order_by('quantity')[:6],
            'recent_orders': orders.select_related('product', 'region').order_by('-created_at')[:8],
            'pending_payouts': Transaction.objects.filter(status=Transaction.Status.PROCESS).count(),
            'pending_reviews': Review.objects.filter(is_published=False).count(),
            'new_orders': status_counts.get('new', 0),
        }

    def index(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), **self.dashboard_context()}
        return super().index(request, extra_context)

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        if app_label:
            return app_list
        groups = {
            'orders': {'name': _('Buyurtmalar'), 'app_label': 'orders', 'models': []},
            'catalog': {'name': _('Katalog'), 'app_label': 'catalog', 'models': []},
            'people': {'name': _('Foydalanuvchilar'), 'app_label': 'people', 'models': []},
            'finance': {'name': _("Moliya va sozlamalar"), 'app_label': 'finance', 'models': []},
        }
        placement = {
            'Order': 'orders', 'OrderNewProxyModel': 'orders', 'OrderReadyProxyModel': 'orders',
            'OrderDeliverProxyModel': 'orders', 'OrderDeliveredProxyModel': 'orders',
            'OrderCantPhoneProxyModel': 'orders', 'OrderBrokenProxyModel': 'orders',
            'OrderCanceledProxyModel': 'orders', 'OrderArchivedProxyModel': 'orders', 'Stream': 'orders',
            'Category': 'catalog', 'Product': 'catalog', 'Review': 'catalog', 'Favorite': 'catalog',
            'User': 'people', 'UserProxyModel': 'people', 'UserOperatorProxyModel': 'people',
            'UserCurrierProxyModel': 'people', 'UserManagerProxyModel': 'people', 'UserAdminProxyModel': 'people',
            'Region': 'people', 'District': 'people',
            'Transaction': 'finance', 'SiteSettings': 'finance', 'Competition': 'finance',
        }
        result = []
        for app in app_list:
            if app['app_label'] != 'apps':
                result.append(app)
                continue
            for model in app['models']:
                groups[placement.get(model['object_name'], 'finance')]['models'].append(model)
        return [group for group in groups.values() if group['models']] + result


admin_site = MyAdminSite()


def site_register(*models, site=None):
    def _model_admin_wrapper(admin_class):
        if not models:
            raise ValueError("At least one model must be passed to register.")

        admin_site.register(models, admin_class=admin_class)
        return admin_class

    return _model_admin_wrapper
