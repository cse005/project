import logging
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from kisan1.models import (
    FarmerProfile,
    LaborProfile,
    LeaseProfile,
    PesticideProfile,
    ToolsProfile,
    TractorProfile,
    UserRegistration,
)
from kisan1.views.shared import (
    announce_otp,
    can_attempt_login,
    can_send_otp,
    clear_login_attempts,
    create_otp_session_payload,
    get_otp_remaining_seconds,
    is_debug_mode,
    is_otp_valid,
    is_valid_mobile,
    is_valid_name,
    register_failed_login_attempt,
    send_real_otp_sms,
)

logger = logging.getLogger(__name__)

PASSBOOK_RE = re.compile(r'^[A-Z][0-9]{11}$')
TRACTOR_LICENSE_RE = re.compile(r'^[A-Z]{2}[0-9]{13}$')
PESTICIDE_LICENSE_RE = re.compile(r'^[A-Z0-9\-]{8,20}$')


def _assign_group_for_role(role):
    group, _ = Group.objects.get_or_create(name=f'role_{role}')
    return group


def _session_back_url_key(flow_prefix):
    return f'{flow_prefix}_otp_back_url'


def _clear_otp_session_state(request, flow_prefix):
    request.session.pop(f'{flow_prefix}_otp', None)
    request.session.pop(f'{flow_prefix}_otp_attempts', None)
    request.session.pop(_session_back_url_key(flow_prefix), None)


def _otp_context(request, *, flow_prefix, otp_key, attempts_key, fallback_url_name):
    payload = request.session.get(otp_key)
    return {
        'attempts_remaining': max(settings.OTP_ATTEMPT_LIMIT - int(request.session.get(attempts_key, 0)), 0),
        'back_url': request.session.get(_session_back_url_key(flow_prefix)) or reverse(fallback_url_name),
        'otp_attempt_limit': settings.OTP_ATTEMPT_LIMIT,
        'otp_remaining_seconds': get_otp_remaining_seconds(payload) or 0,
    }


def _redirect_back_to_origin(request, flow_prefix, fallback_url_name):
    return HttpResponseRedirect(request.session.get(_session_back_url_key(flow_prefix)) or reverse(fallback_url_name))


def _clear_otp_and_redirect(request, flow_prefix, fallback_url_name):
    response = _redirect_back_to_origin(request, flow_prefix, fallback_url_name)
    _clear_otp_session_state(request, flow_prefix)
    return response


def _required_value(request, field_name):
    return (request.POST.get(field_name) or '').strip()


def _is_valid_int(value, *, minimum=0):
    try:
        return int(value) >= minimum
    except (TypeError, ValueError):
        return False


def _is_valid_float(value, *, minimum=0.0):
    try:
        return float(value) >= minimum
    except (TypeError, ValueError):
        return False


def _render_registration_error(request, template_name, message):
    messages.error(request, message)
    return render(request, template_name)


def _missing_fields_error(request, template_name, field_labels):
    return _render_registration_error(
        request,
        template_name,
        f"Please complete all required fields: {', '.join(field_labels)}.",
    )


def _validate_common_registration_fields(request, template_name):
    required_fields = {
        'name': 'Full name',
        'age': 'Age',
        'mobile': 'Mobile number',
        'pincode': 'Pincode',
        'state': 'State',
        'district': 'District',
        'mandal': 'Mandal',
        'village': 'Village',
    }
    missing_fields = [label for field, label in required_fields.items() if not _required_value(request, field)]
    if missing_fields:
        return _missing_fields_error(request, template_name, missing_fields)

    if not is_valid_name(_required_value(request, 'name')):
        return _render_registration_error(request, template_name, "Name should contain only letters and spaces (min 3 chars).")

    if not is_valid_mobile(_required_value(request, 'mobile')):
        return _render_registration_error(request, template_name, "Enter a valid 10-digit mobile number.")

    if not _is_valid_int(_required_value(request, 'age'), minimum=18):
        return _render_registration_error(request, template_name, "Enter a valid age of 18 or above.")

    return None


def _validate_farmer_registration(request, template_name):
    missing_fields = [label for field, label in {'gender': 'Gender', 'passbook': 'Passbook number'}.items() if not _required_value(request, field)]
    if missing_fields:
        return _missing_fields_error(request, template_name, missing_fields)

    if not PASSBOOK_RE.fullmatch(_required_value(request, 'passbook').upper()):
        return _render_registration_error(request, template_name, "Passbook number must be 1 capital letter followed by 11 digits.")

    return None


def _validate_tractor_registration(request, template_name):
    required_fields = {
        'total_experience': 'Total experience',
        'base_wage': 'Base wage per hour',
        'license_id': 'Driving license ID',
    }
    missing_fields = [label for field, label in required_fields.items() if not _required_value(request, field)]
    if missing_fields:
        return _missing_fields_error(request, template_name, missing_fields)

    if not _is_valid_int(_required_value(request, 'total_experience'), minimum=0):
        return _render_registration_error(request, template_name, "Total experience must be a valid number.")

    if not _is_valid_int(_required_value(request, 'base_wage'), minimum=1):
        return _render_registration_error(request, template_name, "Base wage must be at least 1.")

    if not TRACTOR_LICENSE_RE.fullmatch(_required_value(request, 'license_id').upper()):
        return _render_registration_error(request, template_name, "Driving license ID must contain 2 capital letters followed by 13 digits.")

    selected_services = request.POST.getlist('services')
    if not selected_services:
        return _render_registration_error(request, template_name, "Please select at least one service.")

    for service in selected_services:
        experience = _required_value(request, f'exp_{service}')
        wage = _required_value(request, f'wage_{service}')
        if not experience or not wage:
            return _render_registration_error(request, template_name, f"Provide experience and wage for {service}.")
        if not _is_valid_int(experience, minimum=0) or not _is_valid_int(wage, minimum=1):
            return _render_registration_error(request, template_name, f"Provide valid experience and wage values for {service}.")

    return None


def _validate_labor_registration(request, template_name):
    required_fields = {
        'gender': 'Gender',
        'wage_amount': 'Wage amount',
        'wage_type': 'Wage type',
    }
    missing_fields = [label for field, label in required_fields.items() if not _required_value(request, field)]
    if missing_fields:
        return _missing_fields_error(request, template_name, missing_fields)

    if not _is_valid_int(_required_value(request, 'wage_amount'), minimum=1):
        return _render_registration_error(request, template_name, "Wage amount must be at least 1.")

    selected_skills = request.POST.getlist('skills')
    if not selected_skills:
        return _render_registration_error(request, template_name, "Please select at least one skill.")

    for skill in selected_skills:
        experience = _required_value(request, f'exp_{skill}')
        if not experience:
            return _render_registration_error(request, template_name, f"Provide experience for {skill}.")
        if not _is_valid_int(experience, minimum=0):
            return _render_registration_error(request, template_name, f"Provide a valid experience value for {skill}.")

    return None


def _validate_lease_registration(request, template_name):
    required_fields = {
        'water_resource': 'Water resource',
        'total_land': 'Total land',
        'passbook': 'Passbook number',
    }
    missing_fields = [label for field, label in required_fields.items() if not _required_value(request, field)]
    if missing_fields:
        return _missing_fields_error(request, template_name, missing_fields)

    if not _is_valid_float(_required_value(request, 'total_land'), minimum=0.1):
        return _render_registration_error(request, template_name, "Total land must be greater than zero.")

    if not PASSBOOK_RE.fullmatch(_required_value(request, 'passbook').upper()):
        return _render_registration_error(request, template_name, "Passbook number must be 1 capital letter followed by 11 digits.")

    selected_soils = request.POST.getlist('soils')
    if not selected_soils:
        return _render_registration_error(request, template_name, "Please select at least one soil type.")

    for soil in selected_soils:
        acres = _required_value(request, f'acres_{soil}')
        cost = _required_value(request, f'cost_{soil}')
        readable_soil = soil.replace('_', ' ')
        if not acres or not cost:
            return _render_registration_error(request, template_name, f"Provide acreage and cost for {readable_soil}.")
        if not _is_valid_float(acres, minimum=0.1) or not _is_valid_int(cost, minimum=1):
            return _render_registration_error(request, template_name, f"Provide valid acreage and cost values for {readable_soil}.")

    return None


def _validate_tools_registration(request, template_name):
    if not _required_value(request, 'shop_name'):
        return _render_registration_error(request, template_name, "Shop name is required.")

    selected_tools = request.POST.getlist('tools')
    if not selected_tools:
        return _render_registration_error(request, template_name, "Please select at least one tool.")

    for tool in selected_tools:
        cost = _required_value(request, f'cost_{tool}')
        if not cost:
            return _render_registration_error(request, template_name, f"Provide rent per hour for {tool}.")
        if not _is_valid_int(cost, minimum=1):
            return _render_registration_error(request, template_name, f"Provide a valid rent per hour for {tool}.")

    return None


def _validate_pesticide_registration(request, template_name):
    required_fields = {
        'shop_name': 'Shop name',
        'license_id': 'License ID',
        'since_years': 'Since years',
    }
    missing_fields = [label for field, label in required_fields.items() if not _required_value(request, field)]
    if missing_fields:
        return _missing_fields_error(request, template_name, missing_fields)

    if not PESTICIDE_LICENSE_RE.fullmatch(_required_value(request, 'license_id').upper()):
        return _render_registration_error(request, template_name, "License ID must be 8-20 characters with uppercase letters, numbers, or hyphens.")

    if not _is_valid_int(_required_value(request, 'since_years'), minimum=0):
        return _render_registration_error(request, template_name, "Since years must be a valid number.")

    if not request.POST.getlist('products'):
        return _render_registration_error(request, template_name, "Please select at least one product.")

    return None


ROLE_VALIDATORS = {
    'farmer': _validate_farmer_registration,
    'tractor': _validate_tractor_registration,
    'labor': _validate_labor_registration,
    'lease': _validate_lease_registration,
    'tools': _validate_tools_registration,
    'pesticide': _validate_pesticide_registration,
}


def welcome(request):
    return render(request, 'kisan1/welcome.html')


def register_choice(request):
    return render(request, 'kisan1/register_choice.html')


def logout(request):
    request.session.flush()
    return redirect('welcome')


def handle_registration(request, role, template_name):
    if request.method == 'POST':
        common_error_response = _validate_common_registration_fields(request, template_name)
        if common_error_response:
            return common_error_response

        role_error_response = ROLE_VALIDATORS[role](request, template_name)
        if role_error_response:
            return role_error_response

        name = _required_value(request, 'name')
        mobile = _required_value(request, 'mobile')

        core_data = {
            'age': int(_required_value(request, 'age')),
            'district': _required_value(request, 'district'),
            'is_verified': False,
            'mandal': _required_value(request, 'mandal'),
            'mobile': mobile,
            'name': name,
            'role': role,
            'state': _required_value(request, 'state'),
            'village': _required_value(request, 'village'),
        }

        profile_data = {}

        if role == 'farmer':
            profile_data = {
                'gender': _required_value(request, 'gender'),
                'passbook_number': _required_value(request, 'passbook').upper(),
            }
        elif role == 'tractor':
            selected_services = request.POST.getlist('services')
            services_list = []
            for service in selected_services:
                experience = _required_value(request, f'exp_{service}')
                wage = _required_value(request, f'wage_{service}')
                services_list.append(f"{service} ({experience} Yrs @ Rs. {wage}/hr)")

            profile_data = {
                'driving_license': _required_value(request, 'license_id').upper(),
                'experience': int(_required_value(request, 'total_experience')),
                'gender': 'Not Specified',
                'services': " | ".join(services_list),
                'wage_amount': int(_required_value(request, 'base_wage')),
            }
        elif role == 'labor':
            selected_skills = request.POST.getlist('skills')
            skills_with_exp = []
            for skill in selected_skills:
                experience = _required_value(request, f'exp_{skill}')
                skills_with_exp.append(f"{skill} ({experience} Yrs)")

            profile_data = {
                'gender': _required_value(request, 'gender'),
                'skills': ", ".join(skills_with_exp),
                'wage_amount': int(_required_value(request, 'wage_amount')),
                'wage_type': _required_value(request, 'wage_type'),
            }
        elif role == 'lease':
            selected_soils = request.POST.getlist('soils')
            soil_details_list = []
            for soil in selected_soils:
                acres = _required_value(request, f'acres_{soil}')
                cost = _required_value(request, f'cost_{soil}')
                soil_details_list.append(f"{soil.replace('_', ' ')} ({acres} Acres @ Rs. {cost}/acre)")

            profile_data = {
                'lease_per_day': 0,
                'passbook_number': _required_value(request, 'passbook').upper(),
                'soil_type': " | ".join(soil_details_list),
                'total_land': float(_required_value(request, 'total_land')),
                'water_facility': _required_value(request, 'water_resource'),
            }
        elif role == 'tools':
            selected_tools = request.POST.getlist('tools')
            tools_with_cost = []
            for tool in selected_tools:
                cost = _required_value(request, f'cost_{tool}')
                tools_with_cost.append(f"{tool} (Rs. {cost}/hr)")

            profile_data = {
                'rent_per_hour': 0,
                'shop_name': _required_value(request, 'shop_name'),
                'tools_type': " | ".join(tools_with_cost),
            }
        elif role == 'pesticide':
            selected_products = request.POST.getlist('products')
            profile_data = {
                'license_id': _required_value(request, 'license_id').upper(),
                'products_sold': " | ".join(selected_products),
                'shop_name': _required_value(request, 'shop_name'),
                'since_years': int(_required_value(request, 'since_years')),
            }

        request.session['reg_core'] = core_data
        request.session['reg_profile'] = profile_data
        request.session[_session_back_url_key('reg')] = request.path

        if not can_send_otp(mobile, context='registration'):
            messages.error(request, 'Too many OTP requests. Please wait a few minutes and try again.')
            return render(request, template_name)

        otp_payload = create_otp_session_payload()
        request.session['reg_otp'] = otp_payload

        announce_otp(mobile, otp_payload['code'], context='registration')
        if is_debug_mode():
            logger.info('REGISTRATION OTP for %s is %s', mobile, otp_payload['code'])
        send_real_otp_sms(mobile, otp_payload['code'])
        return redirect('verify_otp')

    return render(request, template_name)


def farmer_register(request):
    return handle_registration(request, 'farmer', 'kisan1/farmer_register.html')


def tractor_register(request):
    return handle_registration(request, 'tractor', 'kisan1/tractor_register.html')


def labor_register(request):
    return handle_registration(request, 'labor', 'kisan1/labor_register.html')


def lease_register(request):
    return handle_registration(request, 'lease', 'kisan1/lease_register.html')


def tools_register(request):
    return handle_registration(request, 'tools', 'kisan1/tools_register.html')


def register_pesticide(request):
    return handle_registration(request, 'pesticide', 'kisan1/register_pesticide.html')


def verify_otp(request):
    otp_payload = request.session.get('reg_otp')
    if not otp_payload:
        messages.error(request, 'Please complete registration again to request a new OTP.')
        return _redirect_back_to_origin(request, 'reg', 'register_choice')

    attempts = int(request.session.get('reg_otp_attempts', 0))
    if attempts >= settings.OTP_ATTEMPT_LIMIT:
        messages.error(request, 'Too many invalid OTP attempts. Please register again.')
        return _clear_otp_and_redirect(request, 'reg', 'register_choice')

    if request.method == 'POST':
        if get_otp_remaining_seconds(otp_payload) == 0:
            messages.error(request, 'OTP expired. Please request a new OTP.')
            return _clear_otp_and_redirect(request, 'reg', 'register_choice')

        if is_otp_valid(otp_payload, request.POST.get('otp')):
            core = request.session.get('reg_core') or {}
            profile = request.session.get('reg_profile') or {}
            if not core:
                messages.error(request, 'Registration details expired. Please register again.')
                return _redirect_back_to_origin(request, 'reg', 'register_choice')

            user, _ = UserRegistration.objects.update_or_create(
                mobile=core['mobile'],
                role=core['role'],
                defaults=core,
            )
            user.is_verified = True
            user.save(update_fields=['name', 'age', 'mobile', 'role', 'state', 'district', 'mandal', 'village', 'is_verified'])

            if core['role'] == 'farmer':
                FarmerProfile.objects.update_or_create(user=user, defaults=profile)
            elif core['role'] == 'tractor':
                TractorProfile.objects.update_or_create(user=user, defaults=profile)
            elif core['role'] == 'labor':
                LaborProfile.objects.update_or_create(user=user, defaults=profile)
            elif core['role'] == 'lease':
                LeaseProfile.objects.update_or_create(user=user, defaults=profile)
            elif core['role'] == 'tools':
                ToolsProfile.objects.update_or_create(user=user, defaults=profile)
            elif core['role'] == 'pesticide':
                PesticideProfile.objects.update_or_create(user=user, defaults=profile)

            request.session['active_role'] = core['role']
            request.session['mobile'] = user.mobile
            request.session['name'] = user.name
            request.session['otp_verified'] = True
            request.session['role'] = core['role']
            request.session['role_group'] = _assign_group_for_role(core['role']).name
            request.session['user_id'] = user.id
            request.session.pop('reg_core', None)
            request.session.pop('reg_profile', None)
            _clear_otp_session_state(request, 'reg')

            if core['role'] == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=core['role'])

        request.session['reg_otp_attempts'] = attempts + 1
        if request.session['reg_otp_attempts'] >= settings.OTP_ATTEMPT_LIMIT:
            messages.error(request, 'Too many invalid OTP attempts. Please register again.')
            return _clear_otp_and_redirect(request, 'reg', 'register_choice')
        messages.error(request, 'Invalid OTP')

    return render(
        request,
        'kisan1/otp_verification.html',
        _otp_context(
            request,
            flow_prefix='reg',
            otp_key='reg_otp',
            attempts_key='reg_otp_attempts',
            fallback_url_name='register_choice',
        ),
    )


def login_view(request):
    if request.method == 'POST':
        mobile = _required_value(request, 'mobile')
        role = _required_value(request, 'role')

        if not is_valid_mobile(mobile):
            messages.error(request, 'Enter a valid 10-digit mobile number.')
            return render(request, 'kisan1/login.html')

        if not role:
            messages.error(request, 'Please select a role.')
            return render(request, 'kisan1/login.html')

        user_exists = UserRegistration.objects.filter(mobile=mobile, role=role).exists()
        if not user_exists:
            messages.error(request, 'User not registered!')
            return render(request, 'kisan1/login.html')

        if not can_attempt_login(mobile, context='login'):
            messages.error(request, 'Too many failed login attempts. Please wait before trying again.')
            return render(request, 'kisan1/login.html')

        if not can_send_otp(mobile, context='login'):
            messages.error(request, 'Too many OTP requests. Please wait a few minutes and try again.')
            return render(request, 'kisan1/login.html')

        otp_payload = create_otp_session_payload()
        request.session['login_otp'] = otp_payload
        request.session['mobile'] = mobile
        request.session['role'] = role
        request.session[_session_back_url_key('login')] = request.path

        announce_otp(mobile, otp_payload['code'], context='login')
        if is_debug_mode():
            logger.info('LOGIN OTP for %s is %s', mobile, otp_payload['code'])
        send_real_otp_sms(mobile, otp_payload['code'])
        return redirect('verify_otp_login')

    return render(request, 'kisan1/login.html')


def otp_view(request):
    otp_payload = request.session.get('login_otp')
    if not otp_payload:
        messages.error(request, 'Please login again to request a new OTP.')
        return _redirect_back_to_origin(request, 'login', 'login')

    attempts = int(request.session.get('login_otp_attempts', 0))
    if attempts >= settings.OTP_ATTEMPT_LIMIT:
        messages.error(request, 'Too many invalid OTP attempts. Please login again.')
        return _clear_otp_and_redirect(request, 'login', 'login')

    if request.method == 'POST':
        if get_otp_remaining_seconds(otp_payload) == 0:
            messages.error(request, 'OTP expired. Please login again to request a new OTP.')
            return _clear_otp_and_redirect(request, 'login', 'login')

        if is_otp_valid(otp_payload, request.POST.get('otp')):
            mobile = request.session.get('mobile')
            role = request.session.get('role')
            user = get_object_or_404(UserRegistration, mobile=mobile, role=role)

            request.session['active_role'] = role
            request.session['name'] = user.name
            request.session['otp_verified'] = True
            request.session['role_group'] = _assign_group_for_role(role).name
            request.session['user_id'] = user.id
            _clear_otp_session_state(request, 'login')
            clear_login_attempts(mobile, context='login')

            messages.success(request, f"Welcome back, {user.name}!")

            if role == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=role)

        request.session['login_otp_attempts'] = attempts + 1
        mobile = request.session.get('mobile')
        if mobile:
            register_failed_login_attempt(mobile, context='login')
        if request.session['login_otp_attempts'] >= settings.OTP_ATTEMPT_LIMIT:
            messages.error(request, 'Too many invalid OTP attempts. Please login again.')
            return _clear_otp_and_redirect(request, 'login', 'login')
        messages.error(request, 'Invalid OTP')

    return render(
        request,
        'kisan1/otp_verify.html',
        _otp_context(
            request,
            flow_prefix='login',
            otp_key='login_otp',
            attempts_key='login_otp_attempts',
            fallback_url_name='login',
        ),
    )
