from .auth_views import UserChangePasswordView, UserChangeImageView, UserLogautView, UserSettingsView, \
    UserLoginView, UserRegisterView, ProfileView, OperatorDetailView, OperatorOrderListView, OperatorClaimView, \
    OperatorCreateOrderView, CurrierOrderListView, CurrierListView, CurrierOrderDetailView, CurrierTakeOrderView
from .product_views import ProductListByCategoryListView, ProductStatisticView, ProductOrStreamDetailView, \
    MainBaseView, MarketView, ProductQuickView, ReviewCreateView
from .shop_views import StatisticView, StreamCreateView, StreamListView, StreamDeleteView, CreatedSuccessOrderedView, \
    CompetitionListView, FavouriteListView, FavoriteView, OrderListView, OrderDetailView, OrderSuccessView, CartView, \
    CartAddView, CartUpdateView, CheckoutView
from .utils_views import DiagramView, HeaderSearchView, TransactionCreateView, DistrictListView, CoinsView, \
    InquiriesView
