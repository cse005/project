import re
import logging
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from kisan1.forms import LaborBookingRequestForm, TractorBookingRequestForm

from kisan1.models import (
    BookingStatus,
    LaborBooking,
    LaborProfile,
    LeaseLandRequest,
    LeaseProfile,
    Order,
    PesticideInventory,
    PesticideProfile,
    ShopOrder,
    ToolRentalBooking,
    ToolsProfile,
    TractorBooking,
    TractorProfile,
    UserRegistration,
)
from kisan1.decorators import role_required, session_login_required
from kisan1.services import (
    create_labor_booking,
    create_order_record,
    create_tractor_booking,
    update_order_status,
)
from kisan1.views.shared import check_login, get_logged_in_user

logger = logging.getLogger(__name__)


_CATEGORY_ALIASES = {
    'p&f': ['Pesticide', 'Fertilizer'],
    'p&f&s': ['Pesticide', 'Fertilizer', 'Seeds'],
    'products & fertilizers': ['Pesticide', 'Fertilizer'],
    'products fertilizers': ['Pesticide', 'Fertilizer'],
    'products & fertilizers & seeds': ['Pesticide', 'Fertilizer', 'Seeds'],
}


def _expand_product_categories(raw_category):
    normalized = (raw_category or '').strip().lower()
    if not normalized:
        return []
    if normalized in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[normalized]
    return [raw_category.strip()]


def _sync_shop_available_products(shop_profile):
    if not shop_profile:
        return

    category_values = []
    for category in PesticideInventory.objects.filter(shop=shop_profile.user).values_list('category', flat=True):
        category_values.extend(_expand_product_categories(category))

    deduped_categories = list(dict.fromkeys(category_values))
    shop_profile.products_sold = ' | '.join(deduped_categories)
    shop_profile.save(update_fields=['products_sold'])

def _ensure_role(request, expected_role):
    active_role = request.session.get('active_role') or request.session.get('role')
    return active_role == expected_role


def _reject_self_booking(request, farmer, provider_user):
    if farmer.mobile == provider_user.mobile:
        messages.error(request, "Self-booking is not allowed across your own accounts.")
        return redirect('main_home')
    return None


def _parse_positive_int(value, default=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _sync_booking_and_order_status(booking, *, provider, service_type, status):
    booking.status = status
    booking.save(update_fields=['status'])
    update_order_status(booking=booking, provider=provider, service_type=service_type, status=status)


@session_login_required
@role_required('farmer')
def main_home(request):
    if not check_login(request):
        return redirect('login')

    district = request.GET.get('district', '').strip()
    q = request.GET.get('q', '').strip()

    farmer = get_logged_in_user(request)

    labors_qs = LaborProfile.objects.select_related('user').order_by('-id')
    tractors_qs = TractorProfile.objects.select_related('user').order_by('-id')
    tools_qs = ToolsProfile.objects.select_related('user').order_by('-id')
    lands_qs = LeaseProfile.objects.select_related('user').order_by('-id')
    pesticides_qs = PesticideProfile.objects.select_related('user').order_by('-id')

    if district:
        labors_qs = labors_qs.filter(user__district__icontains=district)
        tractors_qs = tractors_qs.filter(user__district__icontains=district)
        tools_qs = tools_qs.filter(user__district__icontains=district)
        lands_qs = lands_qs.filter(user__district__icontains=district)
        pesticides_qs = pesticides_qs.filter(user__district__icontains=district)

    if q:
        labors_qs = labors_qs.filter(user__name__icontains=q)
        tractors_qs = tractors_qs.filter(user__name__icontains=q)
        tools_qs = tools_qs.filter(user__name__icontains=q)
        lands_qs = lands_qs.filter(user__name__icontains=q)
        pesticides_qs = pesticides_qs.filter(user__name__icontains=q)

    return render(request, 'kisan1/main_home.html', {
        'labors': Paginator(labors_qs, 12).get_page(request.GET.get('labors_page')),
        'tractors': Paginator(tractors_qs, 12).get_page(request.GET.get('tractors_page')),
        'tools': Paginator(tools_qs, 12).get_page(request.GET.get('tools_page')),
        'lands': Paginator(lands_qs, 12).get_page(request.GET.get('lands_page')),
        'pesticides': Paginator(pesticides_qs, 12).get_page(request.GET.get('pesticides_page')),
        'filters': {'district': district, 'q': q},
        'farmer': farmer,
    })


def dashboard(request, role):
    if not check_login(request):
        return redirect('login')

    # 1. Fetch the user profile
    user_profile = get_object_or_404(UserRegistration, mobile=request.session['mobile'], role=role)
    
    # 2. Add 'role' and 'user_profile' to the context explicitly
    context = {
        'user': user_profile, 
        'role': role  # <--- THIS IS THE KEY! This fixes the (ROLE: ) empty bracket.
    }

    if role == 'labor':
        context['work_requests'] = LaborBooking.objects.filter(laborer__user=user_profile).order_by('-created_at')
    elif role == 'tractor':
        context['work_requests'] = TractorBooking.objects.filter(tractor_owner__user=user_profile).order_by('-created_at')
    elif role == 'tools':
        context['work_requests'] = ToolRentalBooking.objects.filter(tool_shop__user=user_profile).order_by('-created_at')
    elif role == 'lease':
        context['work_requests'] = LeaseLandRequest.objects.filter(land__user=user_profile).order_by('-created_at')
    elif role == 'pesticide':
        shop_profile = PesticideProfile.objects.filter(user=user_profile).first()
        if request.method == 'POST' and 'add_product' in request.POST:
            item_name = (request.POST.get('item_name') or '').strip()
            category = (request.POST.get('category') or '').strip()
            price = _parse_positive_int(request.POST.get('price'), default=0)
            stock_quantity = _parse_positive_int(request.POST.get('stock_quantity'), default=0)
            normalized_categories = _expand_product_categories(category)

            if not shop_profile:
                messages.error(request, 'Complete P&F registration first to manage inventory.')
            elif not item_name or not normalized_categories or price <= 0 or stock_quantity <= 0:
                messages.error(request, 'Please provide valid product, category, price, and stock quantity.')
            else:
                inventory_item = None
                created = False
                for normalized_category in normalized_categories:
                    inventory_item, item_created = PesticideInventory.objects.update_or_create(
                        shop=user_profile,
                        item_name=item_name,
                        category=normalized_category,
                        defaults={
                            'price': price,
                            'stock_quantity': stock_quantity,
                        },
                    )
                    created = created or item_created

                _sync_shop_available_products(shop_profile)
                action = 'added' if created else 'updated'
                messages.success(request, f"Product '{inventory_item.item_name}' {action} in inventory.")
                return redirect('dashboard', role='pesticide')

        context['shop'] = shop_profile
        context['inventory'] = PesticideInventory.objects.filter(shop=user_profile).order_by('item_name')
        context['work_requests'] = ShopOrder.objects.filter(shop__user=user_profile).order_by('-created_at')

    templates = {
        'tractor': 'kisan1/dashboard_tractor.html',
        'labor': 'kisan1/dashboard_labour.html',
        'tools': 'kisan1/dashboard_tools.html',
        'lease': 'kisan1/dashboard_lease.html',
        'pesticide': 'kisan1/pfs_dashboard.html',
    }
    return render(request, templates[role], context)

@session_login_required
@role_required('farmer')
def farmer_booking(request):
    if not check_login(request):
        return redirect('login')

    farmer = get_logged_in_user(request)
    labor_bookings = LaborBooking.objects.select_related('laborer__user').filter(farmer=farmer).order_by('-created_at')
    tractor_bookings = TractorBooking.objects.select_related('tractor_owner__user').filter(farmer=farmer).order_by('-created_at')
    tool_bookings = ToolRentalBooking.objects.select_related('tool_shop__user').filter(farmer=farmer).order_by('-created_at')
    lease_requests = LeaseLandRequest.objects.select_related('land__user').filter(farmer=farmer).order_by('-created_at')
    shop_orders = ShopOrder.objects.select_related('shop__user').filter(farmer=farmer).order_by('-created_at')

    context = {
        'labor_bookings': labor_bookings,
        'tractor_bookings': tractor_bookings,
        'tool_bookings': tool_bookings,
        'lease_requests': lease_requests,
        'shop_orders': shop_orders,
        'has_bookings': bool(labor_bookings or tractor_bookings or tool_bookings or lease_requests or shop_orders),
    }
    return render(request, 'kisan1/farmer_booking.html', context)


@session_login_required
@role_required('farmer')
def book_labor(request, labor_id):
    laborer = get_object_or_404(LaborProfile, id=labor_id)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, "Please login to book services.")
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, "Please login with farmer role to place bookings.")
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, laborer.user)
        if blocked:
            return blocked
        form = LaborBookingRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Please provide valid labor booking details.')
            return render(request, 'kisan1/book_labor.html', {'laborer': laborer, 'errors': form.errors})

        duration = form.cleaned_data['duration']
        booking_date = form.cleaned_data['booking_date']
        start_time = form.cleaned_data['start_time']
        location = form.cleaned_data['location']
        total_cost = duration * laborer.wage_amount

        try:
            create_labor_booking(
                farmer=farmer,
                laborer=laborer,
                booking_date=booking_date,
                start_time=start_time,
                duration=duration,
                location=location,
                total_cost=total_cost,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('book_labor', labor_id=labor_id)

        request.session['success_title'] = "Labor Request Sent!"
        request.session['success_msg'] = "Labor is hired but please wait for his approval."
        return redirect('order_success')

    return render(request, 'kisan1/book_labor.html', {'laborer': laborer})


@session_login_required
@role_required('farmer')
def book_tractor(request, tractor_id):
    tractor_owner = get_object_or_404(TractorProfile, id=tractor_id)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, "Please login to book services.")
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, "Please login with farmer role to place bookings.")
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, tractor_owner.user)
        if blocked:
            return blocked
        form = TractorBookingRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Please provide valid tractor booking details.')
            return render(request, 'kisan1/book_tractor.html', {'tractor': tractor_owner, 'errors': form.errors})

        duration_hours = form.cleaned_data['duration_hours']
        booking_date = form.cleaned_data['booking_date']
        start_time = form.cleaned_data['start_time']
        location = form.cleaned_data['location']
        total_cost = duration_hours * tractor_owner.wage_amount

        try:
            create_tractor_booking(
                farmer=farmer,
                tractor_owner=tractor_owner,
                booking_date=booking_date,
                start_time=start_time,
                duration_hours=duration_hours,
                location=location,
                total_cost=total_cost,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('book_tractor', tractor_id=tractor_id)

        request.session['success_title'] = "Tractor Request Sent!"
        request.session['success_msg'] = "Your request is sent to the tractor driver. Please wait for his confirmation."
        return redirect('order_success')

    return render(request, 'kisan1/book_tractor.html', {'tractor': tractor_owner})


@session_login_required
@role_required('farmer')
def book_tool(request, tool_id):
    tool_shop = get_object_or_404(ToolsProfile, id=tool_id)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, "Please login to book services.")
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, "Please login with farmer role to place bookings.")
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, tool_shop.user)
        if blocked:
            return blocked
        receive_date = request.POST.get('receive_date')
        return_date = request.POST.get('return_date')

        tool_prices = {}
        if tool_shop.tools_type:
            for item in tool_shop.tools_type.split('|'):
                match = re.search(r'([A-Za-z]+)\s*\(₹(\d+)/hr\)', item)
                if match:
                    tool_prices[match.group(1)] = int(match.group(2))

        tools_list = []
        total_cost = 0
        for tool in ['Tractor', 'Harvester', 'Plough', 'Rotavator']:
            if request.POST.get(f'tool_{tool}'):
                hours_raw = request.POST.get(f'hours_{tool}', '0')
                try:
                    hours = int(hours_raw) if hours_raw.strip() else 0
                except ValueError:
                    hours = 0
                if hours > 0:
                    price_per_hour = tool_prices.get(tool, 0)
                    total_cost += hours * price_per_hour
                    tools_list.append(f"{tool} ({hours} hrs @ ₹{price_per_hour}/hr)")

        if not tools_list:
            messages.error(request, "Please select at least one tool and enter the required hours.")
            return redirect('book_tool', tool_id=tool_id)

        tools_selected = ", ".join(tools_list)
        home_delivery = request.POST.get('home_delivery') == 'on'
        if home_delivery:
            delivery_location = f"{request.POST.get('state')}, {request.POST.get('district')}, {request.POST.get('mandal')}, {request.POST.get('village')}"
        else:
            delivery_location = "Pickup from Shop"

        ToolRentalBooking.objects.create(
            farmer=farmer,
            tool_shop=tool_shop,
            tools_selected=tools_selected,
            receive_date=receive_date,
            return_date=return_date,
            home_delivery=home_delivery,
            delivery_location=delivery_location,
            total_cost=total_cost,
        )
        create_order_record(
            farmer=farmer,
            provider=tool_shop.user,
            service_type='tools',
            details=tools_selected,
            booking_date=receive_date,
            total_amount=total_cost,
        )

        request.session['success_title'] = "Tools Booked!"
        request.session['success_msg'] = "Tools are booked but please wait for confirmation by the owner."
        return redirect('order_success')

    return render(request, 'kisan1/book_tool.html', {'tool_shop': tool_shop})


@session_login_required
@role_required('farmer')
def request_lease(request, land_id):
    land = get_object_or_404(LeaseProfile, id=land_id)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, "Please login to book services.")
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, "Please login with farmer role to place bookings.")
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, land.user)
        if blocked:
            return blocked
        soil_type_requested = request.POST.get('soil_type_requested', 'Not Specified')
        duration_months = _parse_positive_int(request.POST.get('duration_months', 1), default=1)
        start_date = request.POST.get('start_date')
        message_to_owner = request.POST.get('message_to_owner')

        LeaseLandRequest.objects.create(
            farmer=farmer,
            land=land,
            soil_type_requested=soil_type_requested,
            duration_months=duration_months,
            start_date=start_date,
            message_to_owner=message_to_owner,
        )
        create_order_record(
            farmer=farmer,
            provider=land.user,
            service_type='lease',
            details=message_to_owner,
            booking_date=start_date,
            total_amount=0,
        )

        request.session['success_title'] = "Lease Request Sent!"
        request.session['success_msg'] = "Your request is sent. Wait for owner approval."
        return redirect('order_success')

    return render(request, 'kisan1/request_lease.html', {'land': land})


@session_login_required
@role_required('farmer')
def book_shop(request, shop_id):
    shop = get_object_or_404(PesticideProfile, id=shop_id)
    inventory_items = PesticideInventory.objects.filter(shop=shop.user)

    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, "Please login to book services.")
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, "Please login with farmer role to place bookings.")
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, shop.user)
        if blocked:
            return blocked

        items_ordered = []
        calculated_total_cost = 0

        # Only process items from live inventory
        for item in inventory_items:
            qty_raw = request.POST.get(f'qty_{item.id}', 0)
            quantity = _parse_positive_int(qty_raw, default=0)
            
            if quantity > 0:
                if quantity > item.stock_quantity:
                    messages.error(request, f"Sorry, only {item.stock_quantity} units of {item.item_name} available.")
                    return redirect('book_shop', shop_id=shop_id)
                calculated_total_cost += quantity * item.price
                items_ordered.append(f"{item.item_name} ({quantity} units @ ₹{item.price})")

        if not items_ordered:
            messages.error(request, "Please select at least one item.")
            return redirect('book_shop', shop_id=shop_id)

        display_shop_name = shop.shop_name if shop.shop_name else f"{shop.user.name}'s Shop"
        request.session['temp_cart'] = {
            'shop_id': shop.id,
            'shop_name': display_shop_name,
            'items_ordered': items_ordered,
            'total_cost': calculated_total_cost,
        }
        return redirect('cart')

    return render(request, 'kisan1/book_shop.html', {
        'shop': shop,
        'inventory': inventory_items,
    })


def _update_shop_order_status(booking, status):
    booking.status = status
    booking.save()
    Order.objects.filter(
        user=booking.farmer,
        provider=booking.shop.user,
        service_type='shop',
        details=booking.items_ordered,
    ).update(status=status, total_amount=int(booking.total_cost))


@session_login_required
@role_required('labor')
def accept_labor_booking(request, booking_id):
    if not _ensure_role(request, 'labor'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(LaborBooking, id=booking_id)
    if request.method == 'POST':
        _sync_booking_and_order_status(
            booking,
            provider=booking.laborer.user,
            service_type='labor',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, f"Accepted booking from {booking.farmer.name}!")
    return redirect('dashboard', role='labor')


@session_login_required
@role_required('tractor')
def accept_tractor_booking(request, booking_id):
    if not _ensure_role(request, 'tractor'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(TractorBooking, id=booking_id)
    if request.method == 'POST':
        _sync_booking_and_order_status(
            booking,
            provider=booking.tractor_owner.user,
            service_type='tractor',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, f"Accepted tractor booking from {booking.farmer.name}!")
    return redirect('dashboard', role='tractor')


@session_login_required
@role_required('tools')
def accept_tool_booking(request, booking_id):
    if not _ensure_role(request, 'tools'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(ToolRentalBooking, id=booking_id)
    if request.method == 'POST':
        _sync_booking_and_order_status(
            booking,
            provider=booking.tool_shop.user,
            service_type='tools',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, f"Accepted tool rental from {booking.farmer.name}!")
    return redirect('dashboard', role='tools')


@session_login_required
@role_required('lease')
def accept_lease_request(request, booking_id):
    if not _ensure_role(request, 'lease'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(LeaseLandRequest, id=booking_id)
    if request.method == 'POST':
        _sync_booking_and_order_status(
            booking,
            provider=booking.land.user,
            service_type='lease',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, f"Accepted lease meeting with {booking.farmer.name}!")
    return redirect('dashboard', role='lease')


@session_login_required
@role_required('pesticide')
def accept_shop_order(request, booking_id):
    if not _ensure_role(request, 'pesticide'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(ShopOrder, id=booking_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                for item_str in booking.items_ordered.split(', '):
                    # Parse format safely: "Urea (2 units @ ₹100)" -> "Urea" and "2"
                    product_name = item_str.split(' (')[0].strip()
                    qty_str = item_str.split('(')[1].split(' units')[0]
                    qty = int(qty_str)
                    
                    inventory_item = PesticideInventory.objects.select_for_update().get(
                        shop=booking.shop.user,
                        item_name__iexact=product_name,
                    )
                    
                    if inventory_item.stock_quantity >= qty:
                        inventory_item.stock_quantity -= qty
                        inventory_item.save()
                    else:
                        messages.error(request, f'Insufficient stock for {product_name}.')
                        return redirect('dashboard', role='pesticide')

            # Update status after successful inventory transaction
            _update_shop_order_status(booking, BookingStatus.CONFIRMED)
            messages.success(request, f"Accepted Shop Order from {booking.farmer.name} and updated inventory!")
        except Exception as e:
            logger.error(f"Error processing shop order {booking_id}: {e}")
            messages.error(request, "An error occurred while processing the stock. Please try again.")

    return redirect('dashboard', role='pesticide')


@session_login_required
@role_required('labor')
def reject_labor_booking(request, booking_id):
    if not _ensure_role(request, 'labor'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(LaborBooking, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.laborer.user,
        service_type='labor',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, "Booking Rejected.")
    return redirect('dashboard', role='labor')


@session_login_required
@role_required('tractor')
def reject_tractor_booking(request, booking_id):
    if not _ensure_role(request, 'tractor'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(TractorBooking, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.tractor_owner.user,
        service_type='tractor',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, "Booking Rejected.")
    return redirect('dashboard', role='tractor')


@session_login_required
@role_required('tools')
def reject_tool_booking(request, booking_id):
    if not _ensure_role(request, 'tools'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(ToolRentalBooking, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.tool_shop.user,
        service_type='tools',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, "Rental Request Rejected.")
    return redirect('dashboard', role='tools')


@session_login_required
@role_required('lease')
def reject_lease_request(request, booking_id):
    if not _ensure_role(request, 'lease'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(LeaseLandRequest, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.land.user,
        service_type='lease',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, "Lease Request Rejected.")
    return redirect('dashboard', role='lease')


@session_login_required
@role_required('pesticide')
def reject_shop_order(request, booking_id):
    if not _ensure_role(request, 'pesticide'):
        messages.error(request, "Unauthorized action for this role.")
        return redirect('login')
    booking = get_object_or_404(ShopOrder, id=booking_id)
    _update_shop_order_status(booking, BookingStatus.REJECTED)
    messages.warning(request, "Shop Order Rejected.")
    return redirect('dashboard', role='pesticide')


def booking_success_view(request):
    if not check_login(request):
        return redirect('login')
    title = request.session.pop('success_title', 'Order Confirmed!')
    message = request.session.pop('success_msg', 'Your shop order has been placed successfully.')
    return render(request, 'kisan1/booking_success.html', {'title': title, 'message': message})


def order_success_view(request):
    if not check_login(request):
        return redirect('login')
    title = request.session.pop('success_title', 'Booking Sent Successfully!')
    message = request.session.pop('success_msg', 'Your request has been sent to the owner.')
    return render(request, 'kisan1/order_success.html', {'title': title, 'message': message})


def labor_dashboard(request):
    if not check_login(request):
        return redirect('login')
    user_reg = UserRegistration.objects.get(mobile=request.session.get('mobile'))
    labor_data = LaborProfile.objects.filter(user=user_reg).first()
    work_requests = LaborBooking.objects.filter(laborer=labor_data).order_by('-created_at')
    return render(request, 'kisan1/dashboard_labour.html', {
        'user': user_reg,
        'labor': labor_data,
        'work_requests': work_requests,
    })


@session_login_required
@role_required('farmer')
def cart_view(request):
    if not check_login(request):
        return redirect('login')

    farmer = get_logged_in_user(request)
    cart_data = request.session.get('temp_cart')

    if request.method == 'POST' and 'confirm_checkout' in request.POST and cart_data:
        shop = get_object_or_404(PesticideProfile, id=cart_data['shop_id'])
        shop_order = ShopOrder.objects.create(
            farmer=farmer,
            shop=shop,
            items_ordered=", ".join(cart_data['items_ordered']),
            total_cost=cart_data['total_cost'],
        )
        create_order_record(
            farmer=farmer,
            provider=shop.user,
            service_type='shop',
            details=shop_order.items_ordered,
            total_amount=int(shop_order.total_cost),
        )
        del request.session['temp_cart']

        request.session['success_title'] = "Order Confirmed!"
        request.session['success_msg'] = "Your order is confirmed, but the shop owner has not given approval yet."
        return redirect('booking_success')

    orders = ShopOrder.objects.filter(farmer=farmer).order_by('-created_at')
    return render(request, 'kisan1/cart_orders.html', {'farmer': farmer, 'orders': orders, 'cart_data': cart_data})


@session_login_required
@role_required('farmer')
def cancel_booking(request, type, id):
    if not check_login(request):
        return redirect('login')

    if request.method == 'POST':
        booking = None
        if type == 'tool':
            booking = get_object_or_404(ToolRentalBooking, id=id)
            update_order_status(booking=booking, provider=booking.tool_shop.user, service_type='tools', status=BookingStatus.CANCELLED)
        elif type == 'tractor':
            booking = get_object_or_404(TractorBooking, id=id)
            update_order_status(booking=booking, provider=booking.tractor_owner.user, service_type='tractor', status=BookingStatus.CANCELLED)
        elif type == 'labor':
            booking = get_object_or_404(LaborBooking, id=id)
            update_order_status(booking=booking, provider=booking.laborer.user, service_type='labor', status=BookingStatus.CANCELLED)
        elif type == 'shop':
            booking = get_object_or_404(ShopOrder, id=id)
            _update_shop_order_status(booking, BookingStatus.CANCELLED)
        elif type == 'lease':
            booking = get_object_or_404(LeaseLandRequest, id=id)
            update_order_status(booking=booking, provider=booking.land.user, service_type='lease', status=BookingStatus.CANCELLED)

        if booking:
            booking.status = BookingStatus.CANCELLED
            booking.save()
            messages.info(request, f"Your {type} request has been cancelled.")

    return redirect('farmer_booking')


@staff_member_required
def analytics_dashboard(request):
    totals = Order.objects.aggregate(
        total_bookings=Count('id'),
        total_revenue=Sum('total_amount'),
    )
    by_service = Order.objects.values('service_type').annotate(count=Count('id')).order_by('-count')
    by_status = Order.objects.values('status').annotate(count=Count('id')).order_by('-count')
    tools_demand = ToolRentalBooking.objects.values('tools_selected').annotate(count=Count('id')).order_by('-count')[:8]
    role_activity = UserRegistration.objects.values('role').annotate(count=Count('id')).order_by('-count')
    return render(request, 'kisan1/admin_analytics.html', {
        'total_bookings': totals.get('total_bookings') or 0,
        'total_revenue': totals.get('total_revenue') or 0,
        'by_service': list(by_service),
        'by_status': list(by_status),
        'tools_demand': list(tools_demand),
        'role_activity': list(role_activity),
    })
