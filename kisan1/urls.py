from django.urls import path
from . import views
from .views.admin_helper import create_admin_view
urlpatterns = [
    path('', views.welcome, name='welcome'),
    path('register_choice/', views.register_choice, name='register_choice'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout, name='logout'),

    # OTP
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('verify-otp-login/', views.otp_view, name='verify_otp_login'),
    path('otp-back/', views.otp_back, name='otp_back'),

    # Registration
    path('farmer_register/', views.farmer_register, name='farmer_register'),
    path('tractor_register/', views.tractor_register, name='tractor_register'),
    path('labor_register/', views.labor_register, name='labor_register'),
    path('lease_register/', views.lease_register, name='lease_register'),
    path('tools_register/', views.tools_register, name='tools_register'),
    path('register-pesticide/', views.register_pesticide, name='register_pesticide'),

    # Dashboards & Main Pages
    path('main-home/', views.main_home, name='main_home'),
    path('dashboard/<str:role>/', views.dashboard, name='dashboard'),
    path('dashboard/<str:role>/service-settings/', views.update_service_settings, name='update_service_settings'),
    path('dashboard/tools/add-products/', views.tool_add_products, name='tool_add_products'),
    path('dashboard/tools/inventory/', views.tool_inventory, name='tool_inventory'),
    path('dashboard/tools/change-rate/', views.tool_change_rate, name='tool_change_rate'),
    
    # --- PRO CART & TRACKING PAGE ---
    path('cart/', views.cart_view, name='cart'),

    # Booking Services (Farmer Side)
    path('farmer-booking/', views.farmer_booking, name='farmer_booking'),
    path('book-labor/<int:labor_id>/', views.book_labor, name='book_labor'),
    path('book-tractor/<int:tractor_id>/', views.book_tractor, name='book_tractor'),
    path('book-tool/<int:tool_id>/', views.book_tool, name='book_tool'),
    path('request-lease/<int:land_id>/', views.request_lease, name='request_lease'),
    path('book-shop/<int:shop_id>/', views.book_shop, name='book_shop'),
    
    # Accept Bookings / Orders (Provider Side)
    path('accept-labor/<int:booking_id>/', views.accept_labor_booking, name='accept_labor_booking'),
    path('accept-tractor/<int:booking_id>/', views.accept_tractor_booking, name='accept_tractor_booking'),
    path('accept-tool/<int:booking_id>/', views.accept_tool_booking, name='accept_tool_booking'),
    path('accept-lease/<int:booking_id>/', views.accept_lease_request, name='accept_lease_request'),
    path('accept-shop/<int:booking_id>/', views.accept_shop_order, name='accept_shop_order'),

    # Reject Bookings / Orders (Provider Side)
    path('reject-labor/<int:booking_id>/', views.reject_labor_booking, name='reject_labor_booking'),
    path('reject-tractor/<int:booking_id>/', views.reject_tractor_booking, name='reject_tractor_booking'),
    path('reject-tool/<int:booking_id>/', views.reject_tool_booking, name='reject_tool_booking'),
    path('reject-lease/<int:booking_id>/', views.reject_lease_request, name='reject_lease_request'),
    path('reject-shop/<int:booking_id>/', views.reject_shop_order, name='reject_shop_order'),

    # Cancel Booking Action (Farmer Side)
    path('cancel-booking/<str:type>/<int:id>/', views.cancel_booking, name='cancel_booking'),

    # Success Pages
    path('booking-success/', views.booking_success_view, name='booking_success'),
    path('order-success/', views.order_success_view, name='order_success'),
    path('get-villages/', views.get_villages_by_pincode, name='get_villages'),
    path('get-location/', views.get_location_api, name='get_location_api'),
    path('get-location/', views.get_location_api, name='get_location'), # or however you had it mapped!
    path('admin-analytics/', views.analytics_dashboard, name='admin_analytics'),
    path('create-admin/', create_admin_view),
    path('load-pincodes/', load_pincode_view),
]
