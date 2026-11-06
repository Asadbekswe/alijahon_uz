from apps.admin.apps_admin import site_register
from apps.admin.user_admin import OrderModelAdmin
from apps.models.proxy.proxy import OrderNewProxyModel, OrderReadyProxyModel, OrderDeliverProxyModel, \
    OrderDeliveredProxyModel, \
    OrderCantPhoneProxyModel, OrderBrokenProxyModel, OrderCanceledProxyModel, OrderArchivedProxyModel


@site_register(OrderNewProxyModel)
class OrderNewProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'


@site_register(OrderReadyProxyModel)
class OrderReadyProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'


@site_register(OrderDeliverProxyModel)
class OrderDeliverProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'


@site_register(OrderDeliveredProxyModel)
class OrderDeliveredProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'


@site_register(OrderCantPhoneProxyModel)
class OrderCantPhoneProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'


@site_register(OrderBrokenProxyModel)
class OrderBrokenProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'


@site_register(OrderCanceledProxyModel)
class OrderCanceledProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'


@site_register(OrderArchivedProxyModel)
class OrderArchivedProxyModelAdmin(OrderModelAdmin):
    list_filter = 'region', 'created_at'
