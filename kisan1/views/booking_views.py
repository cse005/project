import re
import logging
from datetime import date
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.utils.translation import gettext as _
from kisan1.forms import (
    LaborBookingRequestForm,
    ServiceSettingsForm,
    ShopItemForm,
    ToolInventoryForm,
    ToolRateUpdateForm,
    TractorBookingRequestForm,
)
from kisan1.models import Inventory

from kisan1.models import (
    BookingStatus,
    LaborBooking,
    LaborProfile,
    LeaseLandRequest,
    LeaseProfile,
    Location,
    Order,
    PesticideInventory,
    PesticideProfile,
    ShopOrder,
    ToolInventory,
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
from kisan1.pincode_data import HIDDEN_PINCODES, is_hidden_pincode

logger = logging.getLogger(__name__)



_HIDDEN_PINCODE_STRINGS = [str(code) for code in HIDDEN_PINCODES]


def _exclude_hidden_pincode_queryset(queryset, *, pincode_field='user__pincode'):
    return queryset.exclude(**{f"{pincode_field}__in": _HIDDEN_PINCODE_STRINGS})


_CATEGORY_ALIASES = {
    'p&f': ['Pesticides', 'Fertilizer'],
    'p&f&s': ['Pesticides', 'Fertilizer', 'Seeds'],
    'products & fertilizers': ['Pesticides', 'Fertilizer'],
    'products fertilizers': ['Pesticides', 'Fertilizer'],
    'products & fertilizers & seeds': ['Pesticides', 'Fertilizer', 'Seeds'],
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
        messages.error(request, _("Self-booking is not allowed across your own accounts."))
        return redirect('main_home')
    return None


def _parse_positive_int(value, default=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


_TOOL_RATE_PATTERN = re.compile(
    r'(?P<tool>.+?)\s*\(\s*Rs\.?\s*(?P<rate>\d+)\s*/\s*(?P<unit>hr|day)\s*\)',
    re.IGNORECASE,
)


def _normalize_tool_name(value):
    return ' '.join((value or '').strip().split())


def _parse_tool_inventory_string(raw_value):
    parsed_items = []
    for raw_item in (raw_value or '').split('|'):
        cleaned_item = raw_item.strip()
        if not cleaned_item:
            continue
        match = _TOOL_RATE_PATTERN.search(cleaned_item)
        if match:
            parsed_items.append({
                'tool_name': _normalize_tool_name(match.group('tool')),
                'rate': int(match.group('rate')),
                'rate_unit': match.group('unit').lower(),
            })
            continue
        parsed_items.append({
            'tool_name': _normalize_tool_name(cleaned_item),
            'rate': 0,
            'rate_unit': 'hr',
        })
    return parsed_items


def _serialize_tool_inventory(items):
    serialized = []
    for item in items:
        if isinstance(item, dict):
            tool_name = item.get('tool_name')
            rate = item.get('rate', 0)
            rate_unit = item.get('rate_unit', 'hr')
        else:
            tool_name = item.tool_name
            rate = item.rate
            rate_unit = item.rate_unit
        normalized_name = _normalize_tool_name(tool_name)
        if not normalized_name:
            continue
        serialized.append(f"{normalized_name} (Rs. {rate}/{rate_unit})")
    return " | ".join(serialized)


def _sync_tools_profile_inventory(tool_profile):
    inventory_items = list(ToolInventory.objects.filter(owner=tool_profile.user).order_by('tool_name'))
    serialized_inventory = _serialize_tool_inventory(inventory_items)
    default_rate = next((item.rate for item in inventory_items if item.rate_unit == 'hr'), 0)
    ToolsProfile.objects.filter(pk=tool_profile.pk).update(
        tools_type=serialized_inventory,
        rent_per_hour=default_rate,
    )
    tool_profile.tools_type = serialized_inventory
    tool_profile.rent_per_hour = default_rate
    return inventory_items


def _ensure_tool_inventory_seeded(tool_profile):
    inventory_qs = ToolInventory.objects.filter(owner=tool_profile.user).order_by('tool_name')
    if inventory_qs.exists():
        return list(inventory_qs)

    parsed_items = _parse_tool_inventory_string(tool_profile.tools_type)
    for item in parsed_items:
        ToolInventory.objects.update_or_create(
            owner=tool_profile.user,
            tool_name=item['tool_name'],
            defaults={
                'rate': item['rate'],
                'rate_unit': item.get('rate_unit', 'hr'),
                'is_available': True,
            },
        )
    return _sync_tools_profile_inventory(tool_profile)


def _extract_tool_names_from_booking_text(booking_text):
    tool_names = []
    for entry in (booking_text or '').split('|'):
        chunk = entry.strip()
        if not chunk:
            continue
        tool_name = chunk.split(':', 1)[0].strip()
        if tool_name:
            tool_names.append(_normalize_tool_name(tool_name))
    return tool_names


def _get_rented_tool_names(user_profile, on_date=None):
    active_date = on_date or date.today()
    rented_names = set()
    bookings = ToolRentalBooking.objects.filter(
        tool_shop__user=user_profile,
        status=BookingStatus.CONFIRMED,
        receive_date__lte=active_date,
        return_date__gte=active_date,
    )
    for booking in bookings:
        rented_names.update(_extract_tool_names_from_booking_text(booking.tools_selected))
    return rented_names


def _get_overlapping_tool_booking_names(user_profile, start_date, end_date):
    overlapping_names = set()
    bookings = ToolRentalBooking.objects.filter(
        tool_shop__user=user_profile,
        status=BookingStatus.CONFIRMED,
        receive_date__lte=end_date,
        return_date__gte=start_date,
    )
    for booking in bookings:
        overlapping_names.update(_extract_tool_names_from_booking_text(booking.tools_selected))
    return overlapping_names


def _get_tool_inventory_rows(user_profile):
    tool_profile = get_object_or_404(ToolsProfile, user=user_profile)
    inventory_items = _ensure_tool_inventory_seeded(tool_profile)
    rented_names = _get_rented_tool_names(user_profile)

    rows = []
    available_items = []
    for item in inventory_items:
        status = 'Rented' if item.tool_name in rented_names else 'Available'
        row = {
            'item': item,
            'status': status,
            'rate_label': f"Rs {item.rate}/{item.rate_unit}",
            'rate_suffix': 'hr' if item.rate_unit == 'hr' else 'day',
        }
        rows.append(row)
        if item.is_available and status == 'Available':
            available_items.append(row)

    return {
        'tool_profile': tool_profile,
        'tool_inventory': rows,
        'available_tool_inventory': available_items,
    }


def _build_tools_dashboard_context(user_profile, *, open_panel=None):
    tool_context = _get_tool_inventory_rows(user_profile)
    tool_context.update({
        'open_panel': open_panel,
        'work_requests': ToolRentalBooking.objects.filter(tool_shop__user=user_profile).order_by('-created_at'),
    })
    return tool_context


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

    labors_qs = _exclude_hidden_pincode_queryset(LaborProfile.objects.select_related('user').order_by('-id'))
    tractors_qs = _exclude_hidden_pincode_queryset(TractorProfile.objects.select_related('user').order_by('-id'))
    tools_qs = _exclude_hidden_pincode_queryset(ToolsProfile.objects.select_related('user').order_by('-id'))
    lands_qs = _exclude_hidden_pincode_queryset(LeaseProfile.objects.select_related('user').order_by('-id'))
    pesticides_qs = _exclude_hidden_pincode_queryset(PesticideProfile.objects.select_related('user').order_by('-id'))

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

    labor_page = Paginator(labors_qs, 12).get_page(request.GET.get('labors_page'))
    tractor_page = Paginator(tractors_qs, 12).get_page(request.GET.get('tractors_page'))
    tool_page = Paginator(tools_qs, 12).get_page(request.GET.get('tools_page'))
    land_page = Paginator(lands_qs, 12).get_page(request.GET.get('lands_page'))
    pesticide_page = Paginator(pesticides_qs, 12).get_page(request.GET.get('pesticides_page'))

    for tool_profile in tool_page.object_list:
        _ensure_tool_inventory_seeded(tool_profile)
        _sync_tools_profile_inventory(tool_profile)

    return render(request, 'kisan1/main_home.html', {
        'labors': labor_page,
        'tractors': tractor_page,
        'tools': tool_page,
        'lands': land_page,
        'pesticides': pesticide_page,
        'filters': {'district': district, 'q': q},
        'farmer': farmer,
    })



def _get_service_settings(user_profile, role):
    if role == 'tractor' and hasattr(user_profile, 'tractor_details'):
        return user_profile.tractor_details.wage_amount
    if role == 'labor' and hasattr(user_profile, 'labor_details'):
        return user_profile.labor_details.wage_amount
    if role == 'tools' and hasattr(user_profile, 'tools_details'):
        return user_profile.tools_details.rent_per_hour
    if role == 'lease' and hasattr(user_profile, 'lease_details'):
        return user_profile.lease_details.lease_per_day
    if role == 'pesticide' and hasattr(user_profile, 'pesticide_details'):
        return user_profile.pesticide_details.service_rate
    return 0


def _set_service_rate(user_profile, role, rate):
    if role == 'tractor' and hasattr(user_profile, 'tractor_details'):
        user_profile.tractor_details.wage_amount = rate
        user_profile.tractor_details.save(update_fields=['wage_amount'])
    elif role == 'labor' and hasattr(user_profile, 'labor_details'):
        user_profile.labor_details.wage_amount = rate
        user_profile.labor_details.save(update_fields=['wage_amount'])
    elif role == 'tools' and hasattr(user_profile, 'tools_details'):
        user_profile.tools_details.rent_per_hour = rate
        user_profile.tools_details.save(update_fields=['rent_per_hour'])
    elif role == 'lease' and hasattr(user_profile, 'lease_details'):
        user_profile.lease_details.lease_per_day = rate
        user_profile.lease_details.save(update_fields=['lease_per_day'])
    elif role == 'pesticide' and hasattr(user_profile, 'pesticide_details'):
        user_profile.pesticide_details.service_rate = rate
        user_profile.pesticide_details.save(update_fields=['service_rate'])


@session_login_required
def update_service_settings(request, role):
    if request.method != 'POST':
        return redirect('dashboard', role=role)

    user_profile = get_object_or_404(UserRegistration, mobile=request.session['mobile'], role=role)
    form = ServiceSettingsForm(request.POST)
    if not form.is_valid():
        messages.error(request, _('Please provide valid service settings values.'))
        return redirect('dashboard', role=role)

    _set_service_rate(user_profile, role, form.cleaned_data['rate'])
    user_profile.is_available = form.cleaned_data['is_available']
    user_profile.service_status = form.cleaned_data['service_status']
    user_profile.save(update_fields=['is_available', 'service_status'])
    messages.success(request, _('Service settings updated successfully.'))
    return redirect('dashboard', role=role)

def dashboard(request, role):
    if not check_login(request):
        return redirect('login')

    # 1. Fetch the user profile
    user_profile = get_object_or_404(UserRegistration, mobile=request.session['mobile'], role=role)
    
    # 2. Add 'role' and 'user_profile' to the context explicitly
    context = {
        'user': user_profile,
        'role': role,
        'current_rate': _get_service_settings(user_profile, role),
        'service_status': user_profile.service_status,
        'is_available': user_profile.is_available,
    }

    if role == 'labor':
        context['work_requests'] = LaborBooking.objects.filter(laborer__user=user_profile).order_by('-created_at')
    elif role == 'tractor':
        context['work_requests'] = TractorBooking.objects.filter(tractor_owner__user=user_profile).order_by('-created_at')
    elif role == 'tools':
        context.update(_build_tools_dashboard_context(user_profile))
    elif role == 'lease':
        context['work_requests'] = LeaseLandRequest.objects.filter(land__user=user_profile).order_by('-created_at')
    elif role == 'pesticide':
        shop_profile = PesticideProfile.objects.filter(user=user_profile).first()
        if request.method == 'POST':
            if not shop_profile:
                messages.error(request, _('Complete P&F registration first to manage inventory.'))
            elif 'add_product' in request.POST:
                item_form = ShopItemForm(request.POST)
                if not item_form.is_valid():
                    messages.error(request, _('Please provide valid product, category, market price, shop price, and stock quantity.'))
                else:
                    item_name = item_form.cleaned_data['item_name']
                    category = item_form.cleaned_data['category']
                    market_price = item_form.cleaned_data['market_price']
                    price = item_form.cleaned_data['price']
                    stock_quantity = item_form.cleaned_data['stock_quantity']
                    normalized_categories = _expand_product_categories(category)

                    inventory_item = None
                    created = False
                    for normalized_category in normalized_categories:
                        inventory_item, item_created = PesticideInventory.objects.update_or_create(
                            shop=user_profile,
                            item_name=item_name,
                            category=normalized_category,
                            defaults={
                                'market_price': market_price,
                                'price': price,
                                'stock_quantity': stock_quantity,
                            },
                        )
                        created = created or item_created

                    _sync_shop_available_products(shop_profile)
                    if created:
                        messages.success(
                            request,
                            _("Product '%(item_name)s' added to inventory.") % {'item_name': inventory_item.item_name},
                        )
                    else:
                        messages.success(
                            request,
                            _("Product '%(item_name)s' updated in inventory.") % {'item_name': inventory_item.item_name},
                        )
                    return redirect('dashboard', role='pesticide')
            elif 'save_shop_price' in request.POST or 'update_product_price' in request.POST:
                item_id = request.POST.get('item_id')
                shop_price = request.POST.get('shop_price') or request.POST.get('new_price')
                try:
                    item = PesticideInventory.objects.get(id=item_id, shop=user_profile)
                    item.price = _parse_positive_int(shop_price, default=item.price)
                    item.save(update_fields=['price'])
                    messages.success(
                        request,
                        _("Updated shop price for '%(item_name)s'.") % {'item_name': item.item_name},
                    )
                except PesticideInventory.DoesNotExist:
                    messages.error(request, _('Unable to update price for this product.'))
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


def _render_tools_dashboard(request, user_profile, *, open_panel=None):
    context = {
        'user': user_profile,
        'role': 'tools',
        'current_rate': _get_service_settings(user_profile, 'tools'),
        'service_status': user_profile.service_status,
        'is_available': user_profile.is_available,
    }
    context.update(_build_tools_dashboard_context(user_profile, open_panel=open_panel))
    return render(request, 'kisan1/dashboard_tools.html', context)


@session_login_required
@role_required('tools')
def tool_add_products(request):
    user_profile = get_object_or_404(UserRegistration, mobile=request.session['mobile'], role='tools')
    if request.method == 'POST':
        tool_form = ToolInventoryForm(request.POST)
        if not tool_form.is_valid():
            messages.error(request, _('Please provide a valid tool name, rate, and billing unit.'))
        else:
            tool_name = tool_form.cleaned_data['tool_name']
            existing_item = ToolInventory.objects.filter(owner=user_profile, tool_name__iexact=tool_name).first()
            defaults = {
                'rate': tool_form.cleaned_data['rate'],
                'rate_unit': tool_form.cleaned_data['rate_unit'],
                'is_available': True,
            }
            if existing_item:
                existing_item.tool_name = tool_name
                existing_item.rate = defaults['rate']
                existing_item.rate_unit = defaults['rate_unit']
                existing_item.is_available = True
                existing_item.save(update_fields=['tool_name', 'rate', 'rate_unit', 'is_available', 'updated_at'])
                messages.success(
                    request,
                    _("Updated '%(tool_name)s' in your tool inventory.") % {'tool_name': existing_item.tool_name},
                )
            else:
                ToolInventory.objects.create(owner=user_profile, tool_name=tool_name, **defaults)
                messages.success(
                    request,
                    _("Added '%(tool_name)s' to your tool inventory.") % {'tool_name': tool_name},
                )
            tool_profile = get_object_or_404(ToolsProfile, user=user_profile)
            _sync_tools_profile_inventory(tool_profile)
            return redirect('tool_add_products')
    return _render_tools_dashboard(request, user_profile, open_panel='add-products')


@session_login_required
@role_required('tools')
def tool_inventory(request):
    user_profile = get_object_or_404(UserRegistration, mobile=request.session['mobile'], role='tools')
    return _render_tools_dashboard(request, user_profile, open_panel='inventory')


@session_login_required
@role_required('tools')
def tool_change_rate(request):
    user_profile = get_object_or_404(UserRegistration, mobile=request.session['mobile'], role='tools')
    if request.method == 'POST':
        form = ToolRateUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, _('Please provide a valid tool and updated rate.'))
            return redirect('tool_change_rate')

        tool_item = get_object_or_404(ToolInventory, id=form.cleaned_data['tool_id'], owner=user_profile)
        rented_names = _get_rented_tool_names(user_profile)
        if tool_item.tool_name in rented_names:
            messages.error(
                request,
                _("'%(tool_name)s' is currently rented and its rate cannot be changed right now.") % {
                    'tool_name': tool_item.tool_name,
                },
            )
            return redirect('tool_change_rate')

        tool_item.rate = form.cleaned_data['rate']
        tool_item.save(update_fields=['rate', 'updated_at'])
        tool_profile = get_object_or_404(ToolsProfile, user=user_profile)
        _sync_tools_profile_inventory(tool_profile)
        messages.success(
            request,
            _("Updated rental rate for '%(tool_name)s'.") % {'tool_name': tool_item.tool_name},
        )
        return redirect('tool_change_rate')

    return _render_tools_dashboard(request, user_profile, open_panel='change-rate')

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
    shop_orders = ShopOrder.objects.select_related('shop__user', 'farmer').filter(farmer=farmer).order_by('-created_at')

    context = {
        'labor_bookings': labor_bookings,
        'tractor_bookings': tractor_bookings,
        'tool_bookings': tool_bookings,
        'lease_requests': lease_requests,
        'shop_orders': shop_orders,
        'has_bookings': bool(labor_bookings or tractor_bookings or tool_bookings or lease_requests or shop_orders),
        'show_language_selector': False,
    }
    return render(request, 'kisan1/farmer_booking.html', context)


@session_login_required
@role_required('farmer')
def book_labor(request, labor_id):
    laborer = get_object_or_404(LaborProfile, id=labor_id)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, _("Please login to book services."))
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, _("Please login with farmer role to place bookings."))
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, laborer.user)
        if blocked:
            return blocked
        form = LaborBookingRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, _('Please provide valid labor booking details.'))
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

        request.session['success_title'] = _("Labor Request Sent!")
        request.session['success_msg'] = _("Labor is hired but please wait for approval.")
        return redirect('order_success')

    return render(request, 'kisan1/book_labor.html', {'laborer': laborer})


@session_login_required
@role_required('farmer')
def book_tractor(request, tractor_id):
    tractor_owner = get_object_or_404(TractorProfile, id=tractor_id)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, _("Please login to book services."))
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, _("Please login with farmer role to place bookings."))
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, tractor_owner.user)
        if blocked:
            return blocked
        form = TractorBookingRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, _('Please provide valid tractor booking details.'))
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

        request.session['success_title'] = _("Tractor Request Sent!")
        request.session['success_msg'] = _("Your request has been sent to the tractor driver. Please wait for confirmation.")
        return redirect('order_success')

    return render(request, 'kisan1/book_tractor.html', {'tractor': tractor_owner})


@session_login_required
@role_required('farmer')
def book_tool(request, tool_id):
    tool_shop = get_object_or_404(ToolsProfile, id=tool_id)
    inventory_items = _ensure_tool_inventory_seeded(tool_shop)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, _("Please login to book services."))
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, _("Please login with farmer role to place bookings."))
            return redirect('login')
        blocked = _reject_self_booking(request, farmer, tool_shop.user)
        if blocked:
            return blocked

        receive_date_raw = (request.POST.get('receive_date') or '').strip()
        return_date_raw = (request.POST.get('return_date') or '').strip()
        try:
            receive_date = date.fromisoformat(receive_date_raw)
            return_date = date.fromisoformat(return_date_raw)
        except ValueError:
            messages.error(request, _("Please choose valid receiving and return dates."))
            return redirect('book_tool', tool_id=tool_id)

        if return_date < receive_date:
            messages.error(request, _("Return date must be on or after the receiving date."))
            return redirect('book_tool', tool_id=tool_id)

        overlapping_names = _get_overlapping_tool_booking_names(tool_shop.user, receive_date, return_date)
        tools_list = []
        total_cost = 0

        for item in inventory_items:
            legacy_tool_key = f'tool_{item.tool_name}'
            if not (request.POST.get(f'tool_{item.id}') or request.POST.get(legacy_tool_key)):
                continue

            duration_raw = (
                request.POST.get(f'duration_{item.id}')
                or request.POST.get(f'hours_{item.tool_name}')
                or request.POST.get(f'days_{item.tool_name}')
            )
            duration = _parse_positive_int(duration_raw, default=0)
            if duration <= 0:
                continue
            if item.rate <= 0:
                messages.error(
                    request,
                    _("'%(tool_name)s' does not have a valid rental rate yet.") % {'tool_name': item.tool_name},
                )
                return redirect('book_tool', tool_id=tool_id)
            if not item.is_available or item.tool_name in overlapping_names:
                messages.error(
                    request,
                    _("'%(tool_name)s' is already booked for the selected dates.") % {'tool_name': item.tool_name},
                )
                return redirect('book_tool', tool_id=tool_id)

            unit_label = 'hrs' if item.rate_unit == 'hr' else 'days'
            total_cost += duration * item.rate
            tools_list.append(f"{item.tool_name}: {duration} {unit_label} @ Rs. {item.rate}/{item.rate_unit}")

        if not tools_list:
            messages.error(request, _("Please select at least one tool and enter the required hours or days."))
            return redirect('book_tool', tool_id=tool_id)

        tools_selected = " | ".join(tools_list)
        home_delivery = request.POST.get('home_delivery') == 'on'
        if home_delivery:
            delivery_parts = [
                (request.POST.get('village') or '').strip(),
                (request.POST.get('mandal') or '').strip(),
                (request.POST.get('district') or '').strip(),
                (request.POST.get('state') or '').strip(),
            ]
            delivery_location = ", ".join([part for part in delivery_parts if part]) or "Home Delivery Requested"
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

        request.session['success_title'] = _("Tools Booked!")
        request.session['success_msg'] = _("Tools are booked, but please wait for confirmation by the owner.")
        return redirect('order_success')

    available_now = _get_rented_tool_names(tool_shop.user)
    available_tools = [
        item for item in inventory_items
        if item.is_available and item.tool_name not in available_now
    ]
    return render(request, 'kisan1/book_tool.html', {
        'tool_shop': tool_shop,
        'available_tools': available_tools,
    })


@session_login_required
@role_required('farmer')
def request_lease(request, land_id):
    land = get_object_or_404(LeaseProfile, id=land_id)
    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, _("Please login to book services."))
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, _("Please login with farmer role to place bookings."))
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

        request.session['success_title'] = _("Lease Request Sent!")
        request.session['success_msg'] = _("Your request has been sent. Please wait for owner approval.")
        return redirect('order_success')

    return render(request, 'kisan1/request_lease.html', {'land': land})


@session_login_required
@role_required('farmer')
def book_shop(request, shop_id):
    shop = get_object_or_404(PesticideProfile.objects.exclude(user__pincode__in=_HIDDEN_PINCODE_STRINGS), id=shop_id)
    inventory_items = PesticideInventory.objects.filter(shop=shop.user)

    if request.method == 'POST':
        if not check_login(request):
            messages.error(request, _("Please login to book services."))
            return redirect('login')

        farmer = get_logged_in_user(request)
        if not _ensure_role(request, 'farmer'):
            messages.error(request, _("Please login with farmer role to place bookings."))
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
                    messages.error(
                        request,
                        _("Sorry, only %(quantity)s units of %(item_name)s are available.") % {
                            'quantity': item.stock_quantity,
                            'item_name': item.item_name,
                        },
                    )
                    return redirect('book_shop', shop_id=shop_id)
                calculated_total_cost += quantity * item.price
                items_ordered.append(f"{item.item_name} ({quantity} units @ Rs. {item.price})")

        if not items_ordered:
            messages.error(request, _("Please select at least one item."))
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
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(LaborBooking, id=booking_id)
    if request.method == 'POST':
        _sync_booking_and_order_status(
            booking,
            provider=booking.laborer.user,
            service_type='labor',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, _("Accepted booking from %(farmer_name)s!") % {'farmer_name': booking.farmer.name})
    return redirect('dashboard', role='labor')


@session_login_required
@role_required('tractor')
def accept_tractor_booking(request, booking_id):
    if not _ensure_role(request, 'tractor'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(TractorBooking, id=booking_id)
    if request.method == 'POST':
        _sync_booking_and_order_status(
            booking,
            provider=booking.tractor_owner.user,
            service_type='tractor',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, _("Accepted tractor booking from %(farmer_name)s!") % {'farmer_name': booking.farmer.name})
    return redirect('dashboard', role='tractor')


@session_login_required
@role_required('tools')
def accept_tool_booking(request, booking_id):
    if not _ensure_role(request, 'tools'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(ToolRentalBooking, id=booking_id)
    if request.method == 'POST':
        selected_names = set(_extract_tool_names_from_booking_text(booking.tools_selected))
        overlapping_names = _get_overlapping_tool_booking_names(
            booking.tool_shop.user,
            booking.receive_date,
            booking.return_date,
        )
        conflicts = sorted(selected_names.intersection(overlapping_names))
        if conflicts:
            messages.error(
                request,
                _("Cannot confirm this booking because these tools are already rented: %(tools)s.") % {
                    'tools': ', '.join(conflicts),
                },
            )
            return redirect('dashboard', role='tools')
        _sync_booking_and_order_status(
            booking,
            provider=booking.tool_shop.user,
            service_type='tools',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, _("Accepted tool rental from %(farmer_name)s!") % {'farmer_name': booking.farmer.name})
    return redirect('dashboard', role='tools')


@session_login_required
@role_required('lease')
def accept_lease_request(request, booking_id):
    if not _ensure_role(request, 'lease'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(LeaseLandRequest, id=booking_id)
    if request.method == 'POST':
        _sync_booking_and_order_status(
            booking,
            provider=booking.land.user,
            service_type='lease',
            status=BookingStatus.CONFIRMED,
        )
        messages.success(request, _("Accepted lease meeting with %(farmer_name)s!") % {'farmer_name': booking.farmer.name})
    return redirect('dashboard', role='lease')


@session_login_required
@role_required('pesticide')
def accept_shop_order(request, booking_id):
    if not _ensure_role(request, 'pesticide'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(ShopOrder, id=booking_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                for item_str in booking.items_ordered.split(', '):
                    # Parse format safely: "Urea (2 units @ Rs. 100)" -> "Urea" and "2"
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
                        messages.error(request, _('Insufficient stock for %(product_name)s.') % {'product_name': product_name})
                        return redirect('dashboard', role='pesticide')

            # Update status after successful inventory transaction
            _update_shop_order_status(booking, BookingStatus.CONFIRMED)
            messages.success(
                request,
                _("Accepted shop order from %(farmer_name)s and updated inventory!") % {'farmer_name': booking.farmer.name},
            )
        except Exception as e:
            logger.error(f"Error processing shop order {booking_id}: {e}")
            messages.error(request, _("An error occurred while processing the stock. Please try again."))

    return redirect('dashboard', role='pesticide')


@session_login_required
@role_required('labor')
def reject_labor_booking(request, booking_id):
    if not _ensure_role(request, 'labor'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(LaborBooking, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.laborer.user,
        service_type='labor',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, _("Booking rejected."))
    return redirect('dashboard', role='labor')


@session_login_required
@role_required('tractor')
def reject_tractor_booking(request, booking_id):
    if not _ensure_role(request, 'tractor'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(TractorBooking, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.tractor_owner.user,
        service_type='tractor',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, _("Booking rejected."))
    return redirect('dashboard', role='tractor')


@session_login_required
@role_required('tools')
def reject_tool_booking(request, booking_id):
    if not _ensure_role(request, 'tools'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(ToolRentalBooking, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.tool_shop.user,
        service_type='tools',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, _("Rental request rejected."))
    return redirect('dashboard', role='tools')


@session_login_required
@role_required('lease')
def reject_lease_request(request, booking_id):
    if not _ensure_role(request, 'lease'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(LeaseLandRequest, id=booking_id)
    _sync_booking_and_order_status(
        booking,
        provider=booking.land.user,
        service_type='lease',
        status=BookingStatus.REJECTED,
    )
    messages.warning(request, _("Lease request rejected."))
    return redirect('dashboard', role='lease')


@session_login_required
@role_required('pesticide')
def reject_shop_order(request, booking_id):
    if not _ensure_role(request, 'pesticide'):
        messages.error(request, _("Unauthorized action for this role."))
        return redirect('login')
    booking = get_object_or_404(ShopOrder, id=booking_id)
    _update_shop_order_status(booking, BookingStatus.REJECTED)
    messages.warning(request, _("Shop order rejected."))
    return redirect('dashboard', role='pesticide')


def booking_success_view(request):
    if not check_login(request):
        return redirect('login')
    title = request.session.pop('success_title', _('Order Confirmed!'))
    message = request.session.pop('success_msg', _('Your shop order has been placed successfully.'))
    return render(request, 'kisan1/booking_success.html', {'title': title, 'message': message})


def order_success_view(request):
    if not check_login(request):
        return redirect('login')
    title = request.session.pop('success_title', _('Booking Sent Successfully!'))
    message = request.session.pop('success_msg', _('Your request has been sent to the owner.'))
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

        request.session['success_title'] = _("Order Confirmed!")
        request.session['success_msg'] = _("Your order is confirmed, but the shop owner has not given approval yet.")
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
            booking_messages = {
                'tool': _("Your tool request has been cancelled."),
                'tractor': _("Your tractor request has been cancelled."),
                'labor': _("Your labor request has been cancelled."),
                'shop': _("Your shop order has been cancelled."),
                'lease': _("Your lease request has been cancelled."),
            }
            messages.info(request, booking_messages.get(type, _("Your request has been cancelled.")))

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

def pesticide_dashboard(request):

    if request.method == 'POST':

        # ✅ ADD PRODUCT
        if 'add_product' in request.POST:
            item_name = request.POST.get('item_name')
            category = request.POST.get('category')
            unit = request.POST.get('unit')
            market_price = request.POST.get('market_price')
            price = request.POST.get('price')
            stock = request.POST.get('stock_quantity')

            Inventory.objects.create(
                user=request.user,
                item_name=item_name,
                category=category,
                unit=unit,
                market_price=market_price,
                price=price,
                stock_quantity=stock
            )

        # ✅ UPDATE PRICE
        if 'update_product_price' in request.POST:
            item_id = request.POST.get('item_id')
            new_price = request.POST.get('new_price')

            item = Inventory.objects.get(id=item_id, user=request.user)
            item.price = new_price
            item.save()

    # GET DATA
    inventory = Inventory.objects.filter(user=request.user)

    return render(request, 'kisan1/dashboard_labor.html', {
        'inventory': inventory
    })
