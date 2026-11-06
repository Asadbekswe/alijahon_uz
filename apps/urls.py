from django.urls import path, re_path

from apps.views import MainBaseView, UserLoginView, UserLogautView, ProductOrStreamDetailView, \
    ProductListByCategoryListView, TransactionCreateView, HeaderSearchView, FavoriteView, FavouriteListView, \
    OrderListView, UserChangeImageView, UserSettingsView, UserChangePasswordView, CreatedSuccessOrderedView, \
    DiagramView, DistrictListView, CompetitionListView, CoinsView, StreamListView, StreamCreateView, StatisticView, \
    ProductStatisticView, MarketView, InquiriesView, OperatorDetailView, OperatorOrderListView, \
    OperatorCreateOrderView, CurrierOrderListView, CurrierListView, CurrierOrderDetailView, UserRegisterView, \
    ProfileView, OperatorClaimView, CurrierTakeOrderView, ProductQuickView, ReviewCreateView, StreamDeleteView, \
    OrderDetailView, OrderSuccessView, CartView, CartAddView, CartUpdateView, CheckoutView

urlpatterns = [
    path('', MainBaseView.as_view(), name='main_base'),

    # auth
    path('login/', UserLoginView.as_view(), name='login_page'),
    path('register/', UserRegisterView.as_view(), name='register_page'),
    path('logout/', UserLogautView.as_view(), name='logaut_page'),

    # catalog
    path('stream/<int:pk>/', ProductOrStreamDetailView.as_view(), name='stream_detail'),
    path('product-detail/<str:slug>/', ProductOrStreamDetailView.as_view(), name='product_detail'),
    path('product-detail/<str:slug>/quick/', ProductQuickView.as_view(), name='product_quick_view'),
    path('product-detail/<str:slug>/review/', ReviewCreateView.as_view(), name='product_review'),
    re_path(r'^category/(?P<slug>[\w\-]+)/$', ProductListByCategoryListView.as_view(), name='category_by_slug'),
    path('category/', ProductListByCategoryListView.as_view(), name='category_list'),
    path('search/', HeaderSearchView.as_view(), name='search'),

    # cart & checkout
    path('cart/', CartView.as_view(), name='cart_page'),
    path('cart/add/', CartAddView.as_view(), name='cart_add'),
    path('cart/update/', CartUpdateView.as_view(), name='cart_update'),
    path('checkout/', CheckoutView.as_view(), name='checkout_page'),
    path('order/success/', CreatedSuccessOrderedView.as_view(), name='success_order_page'),
    path('order/thank-you/', OrderSuccessView.as_view(), name='success_order_view'),
    path('get-districts/<int:region_id>', DistrictListView.as_view(), name='get_districts'),

    # Profile
    path('profile/', ProfileView.as_view(), name='profile_page'),
    path('profile/favourite/<int:pk>/', FavoriteView.as_view(), name='add_favourite_page'),
    path('profile/liked-products/', FavouriteListView.as_view(), name='favorite_page'),
    path('profile/ordered-products/', OrderListView.as_view(), name='order_page'),
    path('profile/orders/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('profile/settings/', UserSettingsView.as_view(), name='settings_page'),
    path('profile/settings/image/', UserChangeImageView.as_view(), name='settings_change_image_page'),
    path('profile/settings/change-password/', UserChangePasswordView.as_view(), name='settings_change_page'),
    path('order/list/', OrderListView.as_view(), name='order_list'),

    # Affiliate panel
    path('admin-page/', MarketView.as_view(), name='admin_page'),
    path('admin-page/coins/', CoinsView.as_view(), name='coins_user_list'),
    path('admin-page/diagrams/', DiagramView.as_view(), name='diagrams_page'),
    path('admin-page/competition/', CompetitionListView.as_view(), name='competition_page'),
    path('admin-page/statistika/', StatisticView.as_view(), name='statistika_page'),
    path('admin-page/statistika/<int:pk>', ProductStatisticView.as_view(), name='product_statistic'),
    path('admin-page/stream/', StreamListView.as_view(), name='steam_page'),
    path('admin-page/stream/<int:pk>/delete/', StreamDeleteView.as_view(), name='stream_delete'),
    path('admin-page/market/', MarketView.as_view(), name='market_page'),
    re_path(r'^admin-page/market/(?P<slug>[\w\-]+)/$', MarketView.as_view(), name='market_by_slug'),
    path('admin-page/requests/', InquiriesView.as_view(), name='inquiries_page'),
    path('admin-page/create-stream/', StreamCreateView.as_view(), name='create_stream_page'),
    path('payment/', TransactionCreateView.as_view(), name='payment_page'),

    # Operator page
    path('operator-page/add/', OperatorCreateOrderView.as_view(), name='operator_add_order'),
    path('operator-page/', OperatorOrderListView.as_view(), name='operator_page'),
    path('operator-page/<str:status>/', OperatorOrderListView.as_view(), name='operator_status_page'),
    path('operator/detail/<int:pk>/', OperatorDetailView.as_view(), name='operator_detail'),
    path('operator/claim/<int:pk>/', OperatorClaimView.as_view(), name='operator_claim'),

    # Currier page
    path('currier-page/', CurrierListView.as_view(), name='currier_page'),
    path('currier-page/orders/', CurrierOrderListView.as_view(), name='currier_order_page'),
    path('currier-page/take/<int:pk>/', CurrierTakeOrderView.as_view(), name='currier_take'),
    path('currier-page/detail/<int:pk>/', CurrierOrderDetailView.as_view(), name='currier_detail_page'),
]
