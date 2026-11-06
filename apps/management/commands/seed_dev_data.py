"""
Idempotent development seed: regions, accounts, catalog with images, reviews, streams, orders.

    python manage.py seed_dev_data

Every object is looked up by a natural key (phone, slug, name, reserved phone range for orders), so running the
command again updates rows in place instead of duplicating them. Refuses to run with DEBUG off unless forced.
"""
import os
import random
from datetime import date, timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.management.seed_images import render_product
from apps.models import Category, Competition, District, Order, Product, ProductImage, Region, Review, SiteSettings, \
    Stream, Transaction, User

REGIONS = {
    'Toshkent shahri': ['Yunusobod', 'Chilonzor', 'Mirzo Ulug\'bek', 'Yakkasaroy', 'Shayxontohur', 'Sergeli'],
    'Toshkent viloyati': ['Zangiota', 'Qibray', 'Chirchiq', 'Olmaliq', 'Bo\'stonliq'],
    'Andijon': ['Andijon shahri', 'Asaka', 'Xonobod', 'Shahrixon'],
    'Farg\'ona': ['Farg\'ona shahri', 'Qo\'qon', 'Marg\'ilon', 'Rishton'],
    'Namangan': ['Namangan shahri', 'Chust', 'Pop', 'Uchqo\'rg\'on'],
    'Samarqand': ['Samarqand shahri', 'Urgut', 'Kattaqo\'rg\'on', 'Pastdarg\'om'],
    'Buxoro': ['Buxoro shahri', 'G\'ijduvon', 'Kogon', 'Vobkent'],
    'Navoiy': ['Navoiy shahri', 'Zarafshon', 'Karmana'],
    'Qashqadaryo': ['Qarshi', 'Shahrisabz', 'Kitob', 'G\'uzor'],
    'Surxondaryo': ['Termiz', 'Denov', 'Sherobod'],
    'Jizzax': ['Jizzax shahri', 'Zomin', 'G\'allaorol'],
    'Sirdaryo': ['Guliston', 'Yangiyer', 'Sirdaryo tumani'],
    'Xorazm': ['Urganch', 'Xiva', 'Hazorasp'],
    'Qoraqalpog\'iston': ['Nukus', 'Qo\'ng\'irot', 'Beruniy'],
}

# name, slug, description, card colour, background, icon shape (shape, variant)
CATEGORIES = [
    ('Elektronika', 'elektronika', 'Smartfonlar, quloqchinlar, gadjetlar', '#3b5bdb', '#e7ecf7', ('phone', '')),
    ('Maishiy texnika', 'maishiy-texnika', 'Oshxona va uy uchun texnika', '#e03131', '#fbe9e9', ('box', 'kettle')),
    ('Go\'zallik', 'gozallik', 'Parfyumeriya va parvarish', '#c2185b', '#f8e9ef', ('bottle', 'perfume')),
    ('Sumka va aksessuarlar', 'sumka-va-aksessuarlar', 'Sumkalar, ryukzaklar, hamyonlar', '#8b5e3c', '#f3ece6',
     ('bag', '')),
    ('Uy va interyer', 'uy-va-interyer', 'Qulaylik va bezak buyumlari', '#f08c00', '#fbf1e2', ('lamp', '')),
    ('Sport va salomatlik', 'sport-va-salomatlik', 'Mashg\'ulot uchun jihozlar', '#2f9e44', '#e8f3ea',
     ('dumbbell', '')),
]

# category slug, name, short description, price, old price, payout, stock, shape, variant, colour, bg, featured, specs
PRODUCTS = [
    ('elektronika', 'Nova X12 Pro smartfon 256 GB', '6.7" AMOLED, 120 Hz, 50 MP kamera, 5000 mAh', 4_290_000,
     4_990_000, 180_000, 24, 'phone', '', '#3b5bdb', '#e7ecf7', True,
     {'Ekran': '6.7" AMOLED, 120 Hz', 'Xotira': '8 / 256 GB', 'Kamera': '50 + 12 + 5 MP', 'Batareya': '5000 mAh',
      'Kafolat': '12 oy'}),
    ('elektronika', 'AirTune Pods simsiz quloqchin', 'Shovqinni bekor qilish (ANC), 30 soatgacha ishlash', 389_000,
     529_000, 45_000, 60, 'round', 'buds', '#1c7ed6', '#eaf1f9', True,
     {'Ulanish': 'Bluetooth 5.3', 'ANC': 'Ha, 35 dB gacha', 'Ishlash vaqti': '7 + 23 soat', 'Suvdan himoya': 'IPX4'}),
    ('elektronika', 'Pulse Fit 3 aqlli soat', 'Puls, SpO₂, uyqu nazorati, 100+ sport rejimi', 549_000, 690_000,
     60_000, 35, 'round', 'watch', '#495057', '#eceff1', False,
     {'Ekran': '1.9" AMOLED', 'Batareya': '10 kungacha', 'Suvdan himoya': '5 ATM', 'Mos keladi': 'Android / iOS'}),
    ('elektronika', 'BoomCube portativ kolonka', '20 Vt stereo, chuqur bas, suvdan himoyalangan', 459_000, None,
     50_000, 18, 'cylinder', '', '#7048e8', '#eeeafb', False,
     {'Quvvat': '20 Vt', 'Batareya': '12 soat', 'Himoya': 'IPX7', 'Ulanish': 'Bluetooth 5.1, AUX'}),
    ('elektronika', 'PowerCell 20 000 mAh powerbank', 'Tez quvvatlash 22.5 Vt, ikki USB va Type‑C', 239_000,
     299_000, 30_000, 4, 'slab', 'wide', '#2f3640', '#eceff3', False,
     {'Sig\'im': '20 000 mAh', 'Chiqish': '22.5 Vt PD/QC', 'Portlar': '2× USB‑A, 1× USB‑C', 'Og\'irligi': '360 g'}),
    ('elektronika', 'ZenBook Air 14 noutbuk', 'Intel Core i5, 16 GB RAM, 512 GB SSD, 1.3 kg', 7_890_000, 8_690_000,
     300_000, 9, 'laptop', '', '#5c7cfa', '#ebeefa', True,
     {'Protsessor': 'Intel Core i5‑1335U', 'Xotira': '16 GB / 512 GB SSD', 'Ekran': '14" IPS 2.2K',
      'Og\'irligi': '1.3 kg'}),

    ('maishiy-texnika', 'ThermoPro elektr choynak 1.7 L', 'Haroratni sozlash, 2200 Vt, avtomatik o\'chish', 329_000,
     399_000, 40_000, 40, 'box', 'kettle', '#e03131', '#fbe9e9', True,
     {'Hajmi': '1.7 L', 'Quvvat': '2200 Vt', 'Harorat rejimlari': '40–100 °C', 'Korpus': 'Zanglamaydigan po\'lat'}),
    ('maishiy-texnika', 'CrispAir 5.5 L aerogril', 'Yog\'siz qovurish, 8 avtomatik dastur', 899_000, 1_190_000,
     110_000, 22, 'box', '', '#343a40', '#eceef0', True,
     {'Hajmi': '5.5 L', 'Quvvat': '1700 Vt', 'Dasturlar': '8 ta', 'Harorat': '80–200 °C'}),
    ('maishiy-texnika', 'BlendMax smuzi-blender', '1000 Vt, 1.5 L shisha idish, 6 pichoq', 489_000, None, 55_000, 30,
     'box', 'blender', '#1098ad', '#e3f3f6', False,
     {'Quvvat': '1000 Vt', 'Idish': '1.5 L shisha', 'Tezliklar': '5 + puls', 'Pichoqlar': '6 ta'}),
    ('maishiy-texnika', 'Aroma Lux qahva krujkasi to\'plami', '4 ta keramik krujka, 350 ml', 149_000, 189_000, 20_000,
     75, 'cylinder', 'mug', '#e8590c', '#fbece2', False,
     {'Soni': '4 dona', 'Hajmi': '350 ml', 'Material': 'Keramika', 'Mikroto\'lqinli pech': 'Mos'}),
    ('maishiy-texnika', 'SteamGo vertikal dazmol', '1600 Vt, 30 soniyada tayyor, 260 ml', 359_000, 429_000, 40_000, 0,
     'bottle', 'tall', '#5f3dc4', '#efeafb', False,
     {'Quvvat': '1600 Vt', 'Suv idishi': '260 ml', 'Tayyor bo\'lish': '30 soniya', 'Bug\'': '24 g/min'}),
    ('maishiy-texnika', 'FreshBox oziq-ovqat saqlash idishlari', '10 ta germetik idish, BPA siz', 199_000, None,
     25_000, 50, 'jar', '', '#74b816', '#eef6e3', False,
     {'Soni': '10 dona', 'Material': 'Tritan, BPA siz', 'Hajm': '0.3–2.1 L', 'Idish yuvish mashinasi': 'Mos'}),

    ('gozallik', 'Velour Rose parfyum suvi 50 ml', 'Atirgul, vanil va mushk notalari', 459_000, 590_000, 60_000, 26,
     'bottle', 'perfume', '#c2185b', '#f8e9ef', True,
     {'Hajmi': '50 ml', 'Turi': 'Eau de Parfum', 'Notalar': 'Atirgul, vanil, mushk', 'Barqarorlik': '8–10 soat'}),
    ('gozallik', 'HydraGlow namlovchi krem', 'Gialuron kislotasi va skvalan, 50 ml', 179_000, 229_000, 25_000, 64,
     'jar', '', '#d6a77a', '#f6eee6', False,
     {'Hajmi': '50 ml', 'Teri turi': 'Barcha turlar', 'Tarkibi': 'Gialuron, skvalan, niatsinamid'}),
    ('gozallik', 'Green Ritual o\'simlikli shampun', 'Sulfatsiz, rozmarin va choy daraxti', 89_000, None, 12_000, 120,
     'bottle', '', '#2b8a3e', '#e6f2e8', False,
     {'Hajmi': '400 ml', 'Sulfat': 'Yo\'q', 'Soch turi': 'Yog\'li va normal'}),
    ('gozallik', 'Noir Oud erkaklar atiri 100 ml', 'Oud, charm va bergamot', 629_000, 790_000, 80_000, 14, 'bottle',
     'perfume', '#343a40', '#ecedef', False,
     {'Hajmi': '100 ml', 'Turi': 'Eau de Parfum', 'Notalar': 'Oud, charm, bergamot'}),
    ('gozallik', 'Vitamin C yorituvchi zardob', '15% vitamin C, 30 ml', 159_000, 199_000, 20_000, 3, 'bottle', 'tall',
     '#f59f00', '#fdf3e0', False, {'Hajmi': '30 ml', 'Faol modda': '15% L‑askorbin kislota'}),
    ('gozallik', 'Silk Touch qo\'l kremi to\'plami', '3 xil xushbo\'y, 3 × 75 ml', 99_000, 129_000, 15_000, 80, 'jar',
     '', '#e64980', '#fbe8f0', False, {'Soni': '3 dona', 'Hajmi': '75 ml'}),

    ('sumka-va-aksessuarlar', 'Milano charm qo\'l sumkasi', 'Tabiiy charm, ikki bo\'lim, uzun tasma', 690_000,
     890_000, 90_000, 17, 'bag', '', '#8b5e3c', '#f3ece6', True,
     {'Material': 'Tabiiy charm', 'O\'lchami': '30 × 22 × 12 sm', 'Ichki cho\'ntaklar': '3 ta'}),
    ('sumka-va-aksessuarlar', 'Urban Pack 25 L ryukzak', '15.6" noutbuk bo\'limi, suv o\'tkazmaydi', 349_000, 449_000,
     45_000, 45, 'bag', 'backpack', '#2f9e44', '#e8f3ea', False,
     {'Hajmi': '25 L', 'Noutbuk': '15.6" gacha', 'Material': 'Oxford 900D', 'USB port': 'Bor'}),
    ('sumka-va-aksessuarlar', 'Slim Card charm hamyon', 'RFID himoya, 8 ta karta joyi', 149_000, None, 20_000, 70,
     'slab', '', '#5c3d2e', '#f1ebe7', False, {'Material': 'Tabiiy charm', 'Karta joyi': '8 ta', 'RFID': 'Bor'}),
    ('sumka-va-aksessuarlar', 'Weekender sayohat sumkasi', '40 L, poyabzal bo\'limi bilan', 429_000, 520_000, 55_000,
     12, 'bag', '', '#1864ab', '#e7f0f9', False, {'Hajmi': '40 L', 'Material': 'Neylon', 'Poyabzal bo\'limi': 'Bor'}),
    ('sumka-va-aksessuarlar', 'City Mini ryukzak', 'Kundalik uchun ixcham, 12 L', 219_000, 279_000, 30_000, 38,
     'bag', 'backpack', '#c92a2a', '#fbe9e9', False, {'Hajmi': '12 L', 'Material': 'Poliester'}),
    ('sumka-va-aksessuarlar', 'Classic Steel qo\'l soati', 'Zanglamaydigan po\'lat, safir oyna', 899_000, 1_150_000,
     110_000, 8, 'round', 'watch', '#868e96', '#eff1f3', False,
     {'Mexanizm': 'Yaponiya kvarsi', 'Oyna': 'Safir', 'Suvdan himoya': '5 ATM'}),

    ('uy-va-interyer', 'Nordic stol chirog\'i', 'Iliq LED nur, yorug\'likni sozlash', 279_000, 349_000, 35_000, 33,
     'lamp', '', '#f08c00', '#fbf1e2', True,
     {'Lampochka': 'LED, E27', 'Rang harorati': '2700 K', 'Balandligi': '45 sm'}),
    ('uy-va-interyer', 'Amber Wood xushbo\'y sham', 'Soya mumi, 45 soat yonadi', 119_000, None, 15_000, 90,
     'cylinder', 'candle', '#a0522d', '#f4ece6', False,
     {'Mum': 'Soya', 'Yonish vaqti': '45 soat', 'Hajmi': '220 g'}),
    ('uy-va-interyer', 'Terra keramik krujka', 'Qo\'lda sirlangan, 400 ml', 79_000, 99_000, 10_000, 140, 'cylinder',
     'mug', '#5f8d4e', '#edf3ea', False, {'Hajmi': '400 ml', 'Material': 'Keramika'}),
    ('uy-va-interyer', 'Glow Arc pol chirog\'i', 'Minimalistik dizayn, 160 sm', 649_000, 790_000, 80_000, 6, 'lamp', '',
     '#212529', '#eceef0', False, {'Balandligi': '160 sm', 'Lampochka': 'LED, E27'}),
    ('uy-va-interyer', 'Herb Garden saqlash bankalari', '6 ta shisha banka, bambuk qopqoq', 169_000, 210_000, 20_000,
     55, 'jar', '', '#82c91e', '#f0f7e4', False, {'Soni': '6 dona', 'Hajmi': '500 ml'}),
    ('uy-va-interyer', 'Cozy Lavender sham to\'plami', '3 ta sham, lavanda va paxta', 149_000, 189_000, 18_000, 48,
     'cylinder', 'candle', '#9c36b5', '#f3e8f6', False, {'Soni': '3 dona', 'Yonish vaqti': '3 × 25 soat'}),

    ('sport-va-salomatlik', 'IronGrip 2 × 10 kg gantel', 'Sozlanadigan og\'irlik, rezina qoplama', 589_000, 690_000,
     70_000, 20, 'dumbbell', '', '#364fc7', '#e9ecf8', True,
     {'Og\'irligi': '2 × 10 kg', 'Diskalar': '2.5 / 1.25 kg', 'Dasta': 'Xromlangan'}),
    ('sport-va-salomatlik', 'FlexMat yoga gilamchasi', '6 mm TPE, sirpanmaydi, tasma bilan', 189_000, 239_000,
     25_000, 66, 'dumbbell', 'mat', '#9c36b5', '#f3e8f6', False,
     {'Qalinligi': '6 mm', 'Material': 'TPE', 'O\'lchami': '183 × 61 sm'}),
    ('sport-va-salomatlik', 'HydroSport 1 L suv idishi', 'Vaqt belgilari, BPA siz', 69_000, None, 10_000, 150,
     'bottle', 'sport', '#1098ad', '#e3f3f6', False, {'Hajmi': '1 L', 'Material': 'Tritan, BPA siz'}),
    ('sport-va-salomatlik', 'Pro Match futbol to\'pi', 'FIFA standartidagi o\'lcham 5', 159_000, 199_000, 20_000, 2,
     'round', 'ball', '#222222', '#e9f3ec', False, {'O\'lcham': '5', 'Material': 'PU', 'Tikuv': 'Termal'}),
    ('sport-va-salomatlik', 'Pulse Band fitnes bilaguzuk', 'Qadam, puls va uyqu, 14 kun ishlaydi', 249_000, 329_000,
     30_000, 41, 'round', 'watch', '#2f9e44', '#e8f3ea', False,
     {'Ekran': '1.1" AMOLED', 'Batareya': '14 kun', 'Suvdan himoya': '5 ATM'}),
    ('sport-va-salomatlik', 'Shaker Pro protein idishi', '700 ml, aralashtiruvchi shar bilan', 59_000, 79_000, 8_000,
     95, 'bottle', 'sport', '#e8590c', '#fbece2', False, {'Hajmi': '700 ml', 'Material': 'PP, BPA siz'}),
]

REVIEW_TEXTS = {
    5: ["Juda zo'r mahsulot, kutganimdan ham yaxshi chiqdi!", "Sifati a'lo, yetkazib berish tez bo'ldi. Rahmat!",
        "Ikkinchi marta buyurtma qildim, hammaga tavsiya qilaman.", "Narxiga nisbatan juda yaxshi tanlov."],
    4: ["Yaxshi mahsulot, faqat qadog'i biroz ezilgan edi.", "Hammasi yoqdi, yetkazish bir kun kechikdi.",
        "Sifati yaxshi, rasmdagidek."],
    3: ["O'rtacha. Ishlaydi, lekin kutganimdek emas.", "Yomon emas, ammo narxi biroz qimmatroq."],
}
REVIEWER_NAMES = [('Dilnoza', 'Karimova'), ('Jasur', 'Toshmatov'), ('Malika', 'Yusupova'), ('Bekzod', 'Rahimov'),
                  ('Nigora', 'Saidova'), ('Sardor', 'Aliyev'), ('Shahnoza', 'Ergasheva'), ('Otabek', 'Nazarov')]
CUSTOMER_NAMES = ['Aziza Qodirova', 'Rustam Islomov', 'Kamola Abdullayeva', 'Farrux Usmonov', 'Gulnora Xolmatova',
                  'Sherzod Mirzayev', 'Laylo Hasanova', 'Ulug\'bek Sobirov', 'Madina Ortiqova', 'Javohir Qosimov']

SEED_ORDER_PHONE_PREFIX = '99000'  # orders created by the seed use 99000NNNN numbers (natural key)
SEED_REVIEWER_PHONE_PREFIX = '99100'


class Command(BaseCommand):
    help = 'Create or update realistic development data (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--allow-non-debug', action='store_true',
                            help='Run even when DEBUG is off (never use against production).')
        parser.add_argument('--skip-images', action='store_true', help="Don't (re)generate missing images.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['allow_non_debug']:
            raise CommandError('Refusing to seed with DEBUG off. This command is for development databases only.')
        self.skip_images = options['skip_images']
        self.rng = random.Random(2026)
        with transaction.atomic():
            regions = self.seed_regions()
            self.seed_settings()
            accounts = self.seed_accounts(regions)
            categories = self.seed_categories()
            products = self.seed_products(categories)
            self.seed_reviews(products)
            streams = self.seed_streams(accounts['customer'], products)
            self.seed_orders(products, streams, regions, accounts)
            self.seed_competition()
            self.seed_transactions(accounts['customer'])
        self.stdout.write(self.style.SUCCESS(
            f'Seed complete: {Product.objects.count()} products, {Category.objects.count()} categories, '
            f'{Order.objects.count()} orders, {Review.objects.count()} reviews, {User.objects.count()} users.'))

    # ------------------------------------------------------------------ helpers
    def credential(self, name):
        value = os.getenv(name)
        if not value:
            raise CommandError(f'{name} is not set. Run `make env` or add it to .env (see .env.example).')
        return value

    # ------------------------------------------------------------------ sections
    def seed_regions(self):
        regions = {}
        for region_name, districts in REGIONS.items():
            region, _ = Region.objects.get_or_create(name=region_name)
            regions[region_name] = region
            for district_name in districts:
                District.objects.get_or_create(name=district_name, region=region)
        return regions

    def seed_settings(self):
        settings_obj = SiteSettings.objects.order_by('pk').first() or SiteSettings()
        settings_obj.delivery_price_tashkent = 20_000
        settings_obj.delivery_price_tashkent_region = 30_000
        settings_obj.delivery_price_regions = 40_000
        settings_obj.minimum_sum = 50_000
        settings_obj.operator_sum = 5_000
        settings_obj.save()

    def upsert_user(self, phone, password, **fields):
        user = User.objects.filter(phone=phone).first() or User(phone=phone)
        for key, value in fields.items():
            setattr(user, key, value)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def seed_accounts(self, regions):
        district = District.objects.filter(region=regions['Toshkent shahri'], name='Yunusobod').first()
        admin = self.upsert_user(os.getenv('SEED_ADMIN_PHONE', '900000001'), self.credential('SEED_ADMIN_PASSWORD'),
                                 first_name='Admin', last_name='Alijahon', type=User.Type.ADMIN, is_staff=True,
                                 is_superuser=True)
        customer = self.upsert_user(os.getenv('SEED_CUSTOMER_PHONE', '900000002'),
                                    self.credential('SEED_CUSTOMER_PASSWORD'), first_name='Test',
                                    last_name='Mijoz', type=User.Type.USER, district=district,
                                    address='Amir Temur ko\'chasi, 12-uy', balance=0)
        staff_password = self.credential('SEED_STAFF_PASSWORD')
        operator = self.upsert_user('900000003', staff_password, first_name='Operator', last_name='Test',
                                    type=User.Type.OPERATOR)
        courier = self.upsert_user('900000004', staff_password, first_name='Kuryer', last_name='Test',
                                   type=User.Type.CURRIER)
        return {'admin': admin, 'customer': customer, 'operator': operator, 'courier': courier}

    def attach_image(self, instance, field, filename, data_factory):
        current = getattr(instance, field)
        if current and current.name and current.storage.exists(current.name):
            return False
        if self.skip_images:
            return False
        getattr(instance, field).save(filename, ContentFile(data_factory()), save=False)
        return True

    def seed_categories(self):
        categories = {}
        for position, (name, slug, description, color, bg, (shape, variant)) in enumerate(CATEGORIES):
            category = Category.objects.filter(slug=slug).first() or Category(slug=slug)
            category.name, category.description, category.position = name, description, position
            self.attach_image(category, 'image', f'{slug}.jpg',
                              lambda: render_product(shape, color, bg, variant, seed=position))
            category.save()
            categories[slug] = category
        return categories

    def seed_products(self, categories):
        from django.utils.text import slugify
        products = []
        for index, row in enumerate(PRODUCTS):
            (cat_slug, name, short, price, old_price, payout, stock, shape, variant, color, bg, featured,
             specs) = row
            slug = slugify(name, allow_unicode=True)
            product = Product.objects.filter(slug=slug).first() or Product(slug=slug)
            product.name = name
            product.category = categories[cat_slug]
            product.short_description = short
            product.description = self.description_html(name, short, specs)
            product.price, product.old_price, product.discount_price = price, old_price, payout
            product.specifications = specs
            product.is_featured = featured
            product.is_active = True
            if product.pk is None:
                product.quantity = stock
            self.attach_image(product, 'image', f'{slug}.jpg',
                              lambda: render_product(shape, color, bg, variant, seed=index))
            product.save()
            if not product.images.exists() and not self.skip_images:
                for position, (tint, angle) in enumerate(((bg, -8), ('#f4f4f2', 7))):
                    gallery = ProductImage(product=product, position=position)
                    data = render_product(shape, color, tint, variant, seed=index * 7 + position, angle=angle)
                    gallery.image.save(f'{slug}-{position + 2}.jpg', ContentFile(data), save=False)
                    gallery.save()
            products.append(product)
        # Created-at spread so "new arrivals" differ from "featured"
        now = timezone.now()
        for age, product in enumerate(reversed(products)):
            Product.objects.filter(pk=product.pk).update(created_at=now - timedelta(days=age * 2, hours=age))
        return products

    @staticmethod
    def description_html(name, short, specs):
        rows = ''.join(f'<li><strong>{k}:</strong> {v}</li>' for k, v in specs.items())
        return (f'<p><strong>{name}</strong> — {short}.</p>'
                '<p>Mahsulot rasmiy kafolat bilan yetkaziladi. Buyurtmadan so\'ng operatorimiz siz bilan bog\'lanib, '
                'yetkazib berish vaqtini kelishib oladi. To\'lov mahsulotni qabul qilganda amalga oshiriladi.</p>'
                f'<h3>Asosiy xususiyatlar</h3><ul>{rows}</ul>')

    def seed_reviews(self, products):
        reviewers = [
            self.upsert_user(f'{SEED_REVIEWER_PHONE_PREFIX}{i:04d}', None, first_name=first, last_name=last,
                             type=User.Type.USER)
            for i, (first, last) in enumerate(REVIEWER_NAMES)
        ]
        for index, product in enumerate(products):
            count = (index * 5) % 6  # 0..5 reviews, deterministic
            for reviewer in reviewers[:count]:
                rating = self.rng.choices([5, 4, 3], weights=[6, 3, 1])[0]
                Review.objects.update_or_create(product=product, user=reviewer, defaults={
                    'rating': rating, 'text': self.rng.choice(REVIEW_TEXTS[rating]), 'is_published': True})

    def seed_streams(self, owner, products):
        streams = []
        for product, name, discount in ((products[0], 'Instagram — smartfon', 30_000),
                                        (products[1], 'Telegram kanal — quloqchin', 0),
                                        (products[7], 'TikTok — aerogril', 20_000),
                                        (products[12], 'Instagram — parfyum', 10_000)):
            stream, _ = Stream.objects.update_or_create(owner=owner, name=name, defaults={
                'product': product, 'discount': discount})
            if not stream.visit_count:
                Stream.objects.filter(pk=stream.pk).update(visit_count=self.rng.randint(120, 900))
            streams.append(stream)
        return streams

    def seed_orders(self, products, streams, regions, accounts):
        statuses = ([Order.StatusType.DELIVERED] * 10 + [Order.StatusType.NEW] * 6 + [Order.StatusType.READY] * 3
                    + [Order.StatusType.DELIVERING] * 3 + [Order.StatusType.CANCELED] * 2
                    + [Order.StatusType.CANT_PHONE] * 2 + [Order.StatusType.BROKEN] + [Order.StatusType.ARCHIVED])
        region_list = list(regions.values())
        districts = {r.pk: list(r.districts.all()) for r in region_list}
        now = timezone.now()
        payout_total = 0
        for i in range(72):
            phone = f'{SEED_ORDER_PHONE_PREFIX}{i:04d}'
            stream = streams[i % len(streams)] if i % 3 == 0 else None
            product = stream.product if stream else products[(i * 7) % len(products)]
            status = statuses[i % len(statuses)]
            region = region_list[(i * 5) % len(region_list)]
            quantity = 1 + (i % 4 == 0)
            price = max(product.price - stream.discount, 0) if stream else product.price
            payout = max(product.discount_price - stream.discount, 0) if stream else 0
            customer = accounts['customer'] if i % 6 == 1 else None
            in_delivery = status in (Order.StatusType.DELIVERING, Order.StatusType.DELIVERED, Order.StatusType.BROKEN)
            in_progress = status not in (Order.StatusType.NEW,)
            order, created = Order.objects.update_or_create(phone_number=phone, defaults={
                'full_name': CUSTOMER_NAMES[i % len(CUSTOMER_NAMES)] if not customer else customer.get_full_name(),
                'product': product, 'stream': stream, 'referral_user': stream.owner if stream else None,
                'quantity': quantity, 'price': price, 'payout': payout, 'status': status,
                'is_payout_paid': status == Order.StatusType.DELIVERED and bool(stream),
                'region': region, 'district': (districts[region.pk] or [None])[i % max(len(districts[region.pk]), 1)],
                'address': f'{(i % 40) + 1}-uy', 'user': customer,
                'operator': accounts['operator'] if in_progress else None,
                'currier': accounts['courier'] if in_delivery else None,
                'send_order_date': date.today() + timedelta(days=i % 3) if in_progress else None,
            })
            if created:
                Order.objects.filter(pk=order.pk).update(
                    created_at=now - timedelta(days=(i * 37) % 45, hours=(i * 5) % 24))
            if order.is_payout_paid:
                payout_total += payout * quantity
        # Affiliate balance = credited payouts minus withdrawals that were not cancelled.
        withdrawn = sum(Transaction.objects.filter(user=accounts['customer'])
                        .exclude(status=Transaction.Status.CANCELED).values_list('amount', flat=True))
        User.objects.filter(pk=accounts['customer'].pk).update(balance=max(payout_total - withdrawn, 0))

    def seed_competition(self):
        today = date.today()
        competition = Competition.objects.order_by('pk').first() or Competition()
        competition.title = 'Kuz mavsumi konkursi'
        competition.description = ('<p>Eng ko\'p mahsulot yetkazgan 3 ta hamkorga sovg\'alar: smartfon, '
                                   'aqlli soat va simsiz quloqchin.</p>')
        competition.start_date, competition.end_date = today - timedelta(days=45), today + timedelta(days=15)
        competition.is_active = True
        self.attach_image(competition, 'image', 'competition.jpg',
                          lambda: render_product('round', '#f59f00', '#fdf3e0', 'watch', seed=99))
        competition.save()

    def seed_transactions(self, user):
        for amount, status, card in ((150_000, Transaction.Status.PAID, '8600123412341234'),
                                     (80_000, Transaction.Status.PROCESS, '8600123412341234')):
            Transaction.objects.get_or_create(user=user, amount=amount, card_number=card,
                                              defaults={'status': status})
