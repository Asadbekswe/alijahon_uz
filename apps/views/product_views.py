from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView

from apps.forms import ReviewForm, StreamForm
from apps.models import Category, Product, Stream, Review, Order, Region
from apps.services import register_stream_visit

RECENTLY_VIEWED_KEY = 'recently_viewed'
RECENTLY_VIEWED_LIMIT = 12

SORT_OPTIONS = {
    'new': ('-created_at', 'Yangi'),
    'popular': ('-sold_count', 'Ommabop'),
    'price_asc': ('price', 'Arzonroq'),
    'price_desc': ('-price', 'Qimmatroq'),
    'rating': ('-rating_avg', 'Reyting'),
}


def remember_product(request, product_id):
    viewed = [pk for pk in request.session.get(RECENTLY_VIEWED_KEY, []) if pk != product_id]
    request.session[RECENTLY_VIEWED_KEY] = [product_id, *viewed][:RECENTLY_VIEWED_LIMIT]


def recently_viewed(request, exclude=None):
    ids = [pk for pk in request.session.get(RECENTLY_VIEWED_KEY, []) if pk != exclude]
    if not ids:
        return []
    products = Product.objects.for_cards().in_bulk(ids)
    return [products[pk] for pk in ids if pk in products]


def parse_int(value):
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


class MainBaseView(TemplateView):
    template_name = 'apps/home.html'
    SECTION_CACHE_SECONDS = 120

    def get_sections(self):
        sections = cache.get('home:sections')
        if sections is None:
            cards = Product.objects.for_cards()
            sections = {
                'featured': list(cards.filter(is_featured=True)[:8]),
                'deals': list(cards.filter(old_price__gt=0).order_by('-old_price', 'price')[:12]),
                'new_arrivals': list(cards.order_by('-created_at')[:8]),
                'bestsellers': list(cards.order_by('-sold_count', '-created_at')[:8]),
                'top_categories': list(Category.objects.annotate(
                    product_count=Count('products', filter=Q(products__is_active=True))
                ).filter(product_count__gt=0).order_by('position', 'name')[:8]),
                'stats': {
                    'products': Product.objects.active().count(),
                    'delivered': Order.objects.filter(status=Order.StatusType.DELIVERED).count(),
                    'reviews': Review.objects.filter(is_published=True).count(),
                    'rating': Review.objects.filter(is_published=True).aggregate(v=Avg('rating'))['v'],
                    'regions': Region.objects.count(),
                },
            }
            sections['deals'] = [p for p in sections['deals'] if p.discount_percent][:8]
            cache.set('home:sections', sections, self.SECTION_CACHE_SECONDS)
        return sections

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(self.get_sections())
        ctx['hero_product'] = (ctx['featured'] or ctx['bestsellers'] or [None])[0]
        ctx['recently_viewed'] = recently_viewed(self.request)[:8]
        return ctx


class ProductListByCategoryListView(ListView):
    template_name = 'apps/products/catalog.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_category(self):
        slug = self.kwargs.get('slug')
        if not hasattr(self, '_category'):
            self._category = get_object_or_404(Category, slug=slug) if slug else None
        return self._category

    def get_filters(self):
        params = self.request.GET
        sort = params.get('sort') if params.get('sort') in SORT_OPTIONS else 'new'
        min_price, max_price = parse_int(params.get('min_price')), parse_int(params.get('max_price'))
        if min_price is not None and max_price is not None and min_price > max_price:
            min_price, max_price = max_price, min_price
        return {
            'q': params.get('q', params.get('search', '')).strip()[:100],
            'sort': sort,
            'min_price': min_price,
            'max_price': max_price,
            'in_stock': params.get('in_stock') == '1',
            'on_sale': params.get('on_sale') == '1',
        }

    def get_queryset(self):
        filters = self.get_filters()
        qs = Product.objects.for_cards()
        category = self.get_category()
        if category:
            qs = qs.filter(category=category)
        if filters['q']:
            qs = qs.filter(Q(name__icontains=filters['q']) | Q(short_description__icontains=filters['q'])
                           | Q(category__name__icontains=filters['q']))
        if filters['min_price'] is not None:
            qs = qs.filter(price__gte=filters['min_price'])
        if filters['max_price'] is not None:
            qs = qs.filter(price__lte=filters['max_price'])
        if filters['in_stock']:
            qs = qs.filter(quantity__gt=0)
        if filters['on_sale']:
            qs = qs.filter(old_price__isnull=False, old_price__gt=0)
        order = SORT_OPTIONS[filters['sort']][0]
        return qs.order_by(order, '-pk') if order != '-rating_avg' else qs.order_by('-rating_avg', '-rating_count')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = self.get_filters()
        query = self.request.GET.copy()
        query.pop('page', None)
        ctx.update({
            'category': self.get_category(),
            'filters': filters,
            'sort_options': [(key, _(label)) for key, (_order, label) in SORT_OPTIONS.items()],
            'querystring': query.urlencode(),
            'categories': Category.objects.annotate(
                product_count=Count('products', filter=Q(products__is_active=True))),
            'active_filter_count': sum(filters[k] not in (None, False)
                                       for k in ('min_price', 'max_price', 'in_stock', 'on_sale')),
        })
        return ctx

    def get_template_names(self):
        # Infinite scroll / "load more" asks only for the grid fragment.
        if self.request.headers.get('X-Requested-With') == 'fetch':
            return ['apps/products/_catalog_grid.html']
        return [self.template_name]


class ProductOrStreamDetailView(DetailView):
    template_name = 'apps/products/product_detail.html'
    context_object_name = 'product'

    def get_object(self, queryset=None):
        products = Product.objects.active().select_related('category').with_stats()
        pk = self.kwargs.get('pk')
        self.stream = None
        if pk:
            self.stream = get_object_or_404(Stream.objects.select_related('product'), pk=pk)
            # Count each visitor once per session so refreshes don't inflate affiliate stats.
            seen = set(self.request.session.get('seen_streams', []))
            if pk not in seen:
                register_stream_visit(pk)
                self.request.session['seen_streams'] = [*seen, pk][-50:]
            return get_object_or_404(products, pk=self.stream.product_id)
        return get_object_or_404(products, slug=self.kwargs.get('slug'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        product = self.object
        remember_product(self.request, product.pk)
        price = max(product.price - self.stream.discount, 0) if self.stream else product.price
        compare_at = max(filter(None, [product.old_price, product.price if self.stream else None]), default=None)
        reviews = product.reviews.filter(is_published=True).select_related('user')
        distribution = {row['rating']: row['n'] for row in reviews.values('rating').annotate(n=Count('pk'))}
        total_reviews = sum(distribution.values())
        user = self.request.user
        ctx.update({
            'stream': self.stream,
            'stream_id': self.stream.pk if self.stream else '',
            'price': price,
            'compare_at': compare_at if compare_at and compare_at > price else None,
            'savings': compare_at - price if compare_at and compare_at > price else 0,
            'discount_percent': round((compare_at - price) * 100 / compare_at) if compare_at and compare_at > price
            else 0,
            'gallery': [product.image, *[img.image for img in product.images.all()]],
            'reviews': reviews[:10],
            'rating_distribution': [(star, distribution.get(star, 0),
                                     round(distribution.get(star, 0) * 100 / total_reviews) if total_reviews else 0)
                                    for star in range(5, 0, -1)],
            'related': Product.objects.for_cards().filter(category=product.category_id).exclude(pk=product.pk)[:8],
            'recently_viewed': recently_viewed(self.request, exclude=product.pk)[:8],
            'review_form': ReviewForm(),
            'user_review': product.reviews.filter(user=user).first() if user.is_authenticated else None,
            'specifications': list((product.specifications or {}).items()),
        })
        return ctx


class ProductQuickView(DetailView):
    template_name = 'apps/products/_quick_view.html'
    context_object_name = 'product'

    def get_queryset(self):
        return Product.objects.active().select_related('category').with_stats()


class ReviewCreateView(LoginRequiredMixin, View):
    def post(self, request, slug):
        product = get_object_or_404(Product.objects.active(), slug=slug)
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                Review.objects.update_or_create(product=product, user=request.user, defaults={
                    'rating': int(form.cleaned_data['rating']), 'text': form.cleaned_data['text'].strip()})
                messages.success(request, _("Fikringiz uchun rahmat!"))
            except IntegrityError:
                messages.error(request, _("Fikrni saqlab bo'lmadi, qayta urinib ko'ring."))
        else:
            messages.error(request, _("Iltimos, baho tanlang."))
        return redirect(f'{product.get_absolute_url()}#reviews')


class MarketView(LoginRequiredMixin, ListView):
    template_name = 'apps/market.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_queryset(self):
        qs = Product.objects.for_cards()
        slug = self.kwargs.get('slug')
        if slug is not None:
            qs = qs.filter(category__slug=slug)
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        if self.request.GET.get('category') == 'top':
            return qs.order_by('-sold_count', '-pk')
        return qs.order_by('-discount_price', '-pk')

    def get_context_data(self, *, object_list=None, **kwargs):
        ctx = super().get_context_data(object_list=object_list, **kwargs)
        ctx['categories'] = Category.objects.values('name', 'slug')
        ctx['active_slug'] = self.kwargs.get('slug') or ('top' if self.request.GET.get('category') == 'top' else '')
        ctx['stream_form'] = StreamForm()
        query = self.request.GET.copy()
        query.pop('page', None)
        ctx['querystring'] = query.urlencode()
        return ctx


class ProductStatisticView(LoginRequiredMixin, DetailView):
    queryset = Product.objects.active().select_related('category').with_stats()
    template_name = 'apps/products/product_statistic.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        context['product_stream_count'] = product.streams.count()
        context['owner_stream_count'] = product.streams.filter(owner=self.request.user).count()
        context['status_counts'] = [
            {'status': row['status'], 'label': Order.StatusType(row['status']).label, 'n': row['n']}
            for row in product.orders.values('status').annotate(n=Count('pk')).order_by('-n')]
        context['stream_form'] = StreamForm(initial={'product': product})
        return context
