"""Session based shopping cart. Lines are keyed by product and the stream (affiliate link) it came from."""
from dataclasses import dataclass


from apps.models import Product, Stream
from apps.services import OrderLine

SESSION_KEY = 'cart'
MAX_LINE_QUANTITY = 99


@dataclass
class CartItem:
    key: str
    product: Product
    quantity: int
    stream: Stream | None

    @property
    def unit_price(self):
        return max(self.product.price - self.stream.discount, 0) if self.stream else self.product.price

    @property
    def unit_old_price(self):
        candidates = [p for p in (self.product.old_price, self.product.price) if p]
        best = max(candidates) if candidates else 0
        return best if best > self.unit_price else None

    @property
    def total(self):
        return self.unit_price * self.quantity

    @property
    def savings(self):
        return (self.unit_old_price - self.unit_price) * self.quantity if self.unit_old_price else 0

    @property
    def exceeds_stock(self):
        return self.quantity > self.product.quantity


class Cart:
    def __init__(self, session):
        self.session = session
        self.data = {k: int(v) for k, v in session.get(SESSION_KEY, {}).items()}
        self._items = None

    @staticmethod
    def make_key(product_id, stream_id=None):
        return f'{int(product_id)}:{int(stream_id or 0)}'

    def _save(self):
        self.session[SESSION_KEY] = self.data
        self.session.modified = True
        self._items = None

    def add(self, product, quantity=1, stream_id=None, replace=False):
        if stream_id and not Stream.objects.filter(pk=stream_id, product=product).exists():
            stream_id = None
        key = self.make_key(product.pk, stream_id)
        current = 0 if replace else self.data.get(key, 0)
        new_quantity = min(current + quantity, product.quantity, MAX_LINE_QUANTITY)
        if new_quantity <= 0:
            self.data.pop(key, None)
        else:
            self.data[key] = new_quantity
        self._save()
        return self.data.get(key, 0)

    def set_quantity(self, key, quantity):
        if key not in self.data:
            return 0
        product_id = int(key.split(':')[0])
        stock = Product.objects.filter(pk=product_id, is_active=True).values_list('quantity', flat=True).first() or 0
        quantity = min(max(quantity, 0), stock, MAX_LINE_QUANTITY)
        if quantity == 0:
            self.data.pop(key, None)
        else:
            self.data[key] = quantity
        self._save()
        return quantity

    def remove(self, key):
        self.data.pop(key, None)
        self._save()

    def clear(self):
        self.data = {}
        self._save()

    @property
    def items(self):
        if self._items is None:
            parsed = {}
            for key, qty in self.data.items():
                product_id, stream_id = (int(part) for part in key.split(':'))
                parsed[key] = (product_id, stream_id or None, qty)
            products = Product.objects.filter(pk__in={p for p, _, _ in parsed.values()}, is_active=True) \
                .select_related('category').in_bulk()
            streams = Stream.objects.filter(pk__in={s for _, s, _ in parsed.values() if s}).in_bulk()
            items = []
            for key, (product_id, stream_id, qty) in parsed.items():
                product = products.get(product_id)
                if product is None:
                    continue
                items.append(CartItem(key=key, product=product, quantity=qty, stream=streams.get(stream_id)))
            self._items = items
        return self._items

    def __len__(self):
        return sum(self.data.values())

    def __bool__(self):
        return bool(self.data)

    @property
    def subtotal(self):
        return sum(item.total for item in self.items)

    @property
    def savings(self):
        return sum(item.savings for item in self.items)

    @property
    def has_stock_problems(self):
        return any(item.exceeds_stock for item in self.items)

    def as_order_lines(self):
        return [OrderLine(product_id=i.product.pk, quantity=i.quantity, stream_id=i.stream.pk if i.stream else None)
                for i in self.items]
