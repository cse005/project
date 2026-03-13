import re
import logging

from django.contrib import messages
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render

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
    can_attempt_login,
    can_send_otp,
    clear_login_attempts,
    create_otp_session_payload,
    is_debug_mode,
    is_otp_valid,
    is_valid_mobile,
    is_valid_name,
    register_failed_login_attempt,
    send_real_otp_sms,
    announce_otp,
)

logger = logging.getLogger(__name__)
PASSBOOK_RE = re.compile(r'^[Tt][0-9]{11}$')
LEASE_PASSBOOK_RE = re.compile(r'^[A-Z][0-9]{11}$')
TRACTOR_LICENSE_RE = re.compile(r'^[A-Z]{2}[0-9]{13}$')
PFS_LICENSE_RE = re.compile(r'^[A-Z0-9\-]{8,20}$')


def _assign_group_for_role(role):
    group, _ = Group.objects.get_or_create(name=f'role_{role}')
    return group


def welcome(request):
    return render(request, 'kisan1/welcome.html')


def register_choice(request):
    return render(request, 'kisan1/register_choice.html')


def logout(request):
    request.session.flush()
    return redirect('welcome')




def _is_positive_int(value, min_value=1, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return False
    if parsed < min_value:
        return False
    if max_value is not None and parsed > max_value:
        return False
    return True


def _validate_common_registration_fields(request, template_name, *, name, mobile):
    age_raw = (request.POST.get('age') or '').strip()
    state = (request.POST.get('state') or '').strip()
    district = (request.POST.get('district') or '').strip()
    mandal = (request.POST.get('mandal') or '').strip()
    village = (request.POST.get('village') or '').strip()

    if not name or not mobile or not age_raw or not state or not district or not mandal or not village:
        messages.error(request, "Please fill in all required fields before continuing.")
        return render(request, template_name)

    if not _is_positive_int(age_raw, min_value=18, max_value=100):
        messages.error(request, "Age must be between 18 and 100.")
        return render(request, template_name)

    return None


def _set_otp_back_target(request, session_key):
    request.session[session_key] = request.path


def otp_back(request):
    target = request.session.get('otp_back_url') or request.session.get('login_otp_back_url') or 'register_choice'
    if target == request.path:
        return redirect('register_choice')
    return redirect(target)

def handle_registration(request, role, template_name):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        mobile = request.POST.get('mobile', '').strip()

        if not name or not mobile:
            messages.error(request, "All fields are required!")
            return render(request, template_name)

        if not is_valid_name(name):
            messages.error(request, "Name should contain only letters and spaces (min 3 chars).")
            return render(request, template_name)

        if not is_valid_mobile(mobile):
            messages.error(request, "Enter a valid 10-digit mobile number.")
            return render(request, template_name)

        invalid_common_response = _validate_common_registration_fields(
            request,
            template_name,
            name=name,
            mobile=mobile,
        )
        if invalid_common_response:
            return invalid_common_response

        core_data = {
            'name': name,
            'age': request.POST.get('age') or None,
            'mobile': mobile,
            'role': role,
            'state': request.POST.get('state'),
            'district': request.POST.get('district'),
            'mandal': request.POST.get('mandal'),
            'village': request.POST.get('village'),
            'is_verified': False,
        }

        profile_data = {}

        if role == 'farmer':
            gender = (request.POST.get('gender') or '').strip()
            passbook = (request.POST.get('passbook') or '').strip()
            if not gender or not passbook or not PASSBOOK_RE.fullmatch(passbook):
                messages.error(request, "Enter a valid farmer passbook number (T + 11 digits).")
                return render(request, template_name)
            profile_data = {
                'gender': gender,
                'passbook_number': passbook,
            }
        elif role == 'tractor':
            selected_services = request.POST.getlist('services')
            # NEW: Stop if no services selected
            if not selected_services:
                messages.error(request, "Please select at least one service.")
                return render(request, template_name)
                
            services_list = []
            for service in selected_services:
                exp = request.POST.get(f'exp_{service}')
                wage = request.POST.get(f'wage_{service}')
                if exp and wage:
                    services_list.append(f"{service} ({exp} Yrs @ ₹{wage}/hr)")
                else:
                    services_list.append(service)

            driving_license = (request.POST.get('driving_license') or '').strip()
            base_wage = (request.POST.get('base_wage') or '').strip()
            experience = (request.POST.get('experience') or '').strip()
            if (
                not driving_license
                or not TRACTOR_LICENSE_RE.fullmatch(driving_license.upper())
                or not _is_positive_int(base_wage, min_value=1)
                or not _is_positive_int(experience, min_value=0, max_value=100)
            ):
                messages.error(request, "Please provide valid tractor registration details.")
                return render(request, template_name)

            profile_data = {
                'experience': experience,
                'wage_amount': base_wage,
                'driving_license': driving_license,
                'services': " | ".join(services_list),
                'gender': 'Not Specified',
            }
        elif role == 'labor':
            selected_skills = request.POST.getlist('skills')
            # NEW: Stop if no skills selected
            if not selected_skills:
                messages.error(request, "Please select at least one skill.")
                return render(request, template_name)
                
            skills_with_exp = []
            for skill in selected_skills:
                exp = request.POST.get(f'exp_{skill}')
                if exp:
                    skills_with_exp.append(f"{skill} ({exp} Yrs)")
                else:
                    skills_with_exp.append(skill)

            gender = (request.POST.get('gender') or '').strip()
            wage_amount = (request.POST.get('wage_amount') or '').strip()
            wage_type = (request.POST.get('wage_type') or '').strip()
            if not gender or not wage_type or not _is_positive_int(wage_amount, min_value=1):
                messages.error(request, "Please provide valid labor registration details.")
                return render(request, template_name)

            profile_data = {
                'skills': ", ".join(skills_with_exp),
                'gender': gender,
                'wage_amount': wage_amount,
                'wage_type': wage_type,
            }
        elif role == 'lease':
            selected_soils = request.POST.getlist('soils')
            # NEW: Stop if no soils selected
            if not selected_soils:
                messages.error(request, "Please select at least one soil type.")
                return render(request, template_name)
                
            soil_details_list = []
            for soil in selected_soils:
                acres = request.POST.get(f'acres_{soil}')
                cost = request.POST.get(f'cost_{soil}')
                if acres and cost:
                    soil_details_list.append(f"{soil.replace('_', ' ')} ({acres} Acres @ ₹{cost}/acre)")
                else:
                    soil_details_list.append(soil.replace('_', ' '))

            total_land = (request.POST.get('total_land') or '').strip()
            water_resource = (request.POST.get('water_resource') or '').strip()
            passbook = (request.POST.get('passbook') or '').strip()
            try:
                land_value = float(total_land)
            except (TypeError, ValueError):
                land_value = 0
            if land_value <= 0 or not water_resource or not passbook or not LEASE_PASSBOOK_RE.fullmatch(passbook.upper()):
                messages.error(request, "Please provide valid lease registration details.")
                return render(request, template_name)

            profile_data = {
                'total_land': total_land,
                'water_facility': water_resource,
                'soil_type': " | ".join(soil_details_list),
                'passbook_number': passbook,
                'lease_per_day': 0,
            }
        elif role == 'tools':
            selected_tools = request.POST.getlist('tools')
            # NEW: Stop if no tools selected
            if not selected_tools:
                messages.error(request, "Please select at least one tool.")
                return render(request, template_name)
                
            tools_with_cost = []
            for tool in selected_tools:
                cost = request.POST.get(f'cost_{tool}')
                if cost:
                    tools_with_cost.append(f"{tool} (₹{cost}/hr)")
                else:
                    tools_with_cost.append(tool)

            shop_name = (request.POST.get('shop_name') or '').strip()
            if not shop_name:
                messages.error(request, "Shop name is required for tools registration.")
                return render(request, template_name)

            profile_data = {
                'shop_name': shop_name,
                'tools_type': " | ".join(tools_with_cost),
                'rent_per_hour': 0,
            }
        elif role == 'pesticide':
            selected_products = request.POST.getlist('products')
            # NEW: Stop if no products selected
            if not selected_products:
                messages.error(request, "Please select at least one product.")
                return render(request, template_name)
                
            shop_name = (request.POST.get('shop_name') or '').strip()
            license_id = (request.POST.get('license_id') or '').strip()
            since_years = (request.POST.get('since_years') or '').strip()
            if (
                not shop_name
                or not license_id
                or not PFS_LICENSE_RE.fullmatch(license_id.upper())
                or not _is_positive_int(since_years, min_value=0, max_value=100)
            ):
                messages.error(request, "Please provide valid fertilizer shop registration details.")
                return render(request, template_name)

            profile_data = {
                'shop_name': shop_name,
                'license_id': license_id,
                'since_years': since_years,
                'products_sold': " | ".join(selected_products),
            }

        request.session['reg_core'] = core_data
        request.session['reg_profile'] = profile_data

        if not can_send_otp(mobile, context='registration'):
            messages.error(request, 'Too many OTP requests. Please wait a few minutes and try again.')
            return render(request, template_name)

        # 4-digit OTP
        otp_payload = create_otp_session_payload()
        request.session['reg_otp'] = otp_payload
        _set_otp_back_target(request, 'otp_back_url')

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
    attempts = int(request.session.get('reg_otp_attempts', 0))
    if attempts >= 5:
        request.session.pop('reg_otp', None)
        request.session.pop('reg_otp_attempts', None)
        messages.error(request, 'Too many invalid OTP attempts. Please register again to generate a new OTP.')
        return redirect('register_choice')

    if request.method == 'POST':
        if is_otp_valid(request.session.get('reg_otp'), request.POST.get('otp')):
            core = request.session.get('reg_core')
            prof = request.session.get('reg_profile')

            user, created = UserRegistration.objects.get_or_create(
                mobile=core['mobile'],
                role=core['role'],
                defaults=core,
            )

            if not created:
                for key, value in core.items():
                    setattr(user, key, value)

            user.is_verified = True
            user.save()

            django_group = _assign_group_for_role(core['role'])
            # Keep DB role mapping reusable if Django auth users are added later.
            request.session['active_role'] = core['role']

            if core['role'] == 'farmer':
                FarmerProfile.objects.get_or_create(user=user, defaults=prof)
            elif core['role'] == 'tractor':
                TractorProfile.objects.get_or_create(user=user, defaults=prof)
            elif core['role'] == 'labor':
                LaborProfile.objects.get_or_create(user=user, defaults=prof)
            elif core['role'] == 'lease':
                LeaseProfile.objects.get_or_create(user=user, defaults=prof)
            elif core['role'] == 'tools':
                ToolsProfile.objects.get_or_create(user=user, defaults=prof)
            elif core['role'] == 'pesticide':
                PesticideProfile.objects.get_or_create(user=user, defaults=prof)

            request.session['mobile'] = user.mobile
            request.session['role'] = core['role']
            request.session['otp_verified'] = True
            request.session['user_id'] = user.id
            request.session['role_group'] = django_group.name
            request.session.pop('reg_otp_attempts', None)
            request.session.pop('reg_otp', None)
            request.session.pop('otp_back_url', None)

            if core['role'] == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=core['role'])

        updated_attempts = attempts + 1
        request.session['reg_otp_attempts'] = updated_attempts
        if updated_attempts >= 5:
            request.session.pop('reg_otp', None)
            request.session.pop('reg_otp_attempts', None)
            messages.error(request, 'Too many invalid OTP attempts. Please register again to generate a new OTP.')
            return redirect('register_choice')
        messages.error(request, "Invalid OTP")

    return render(request, 'kisan1/otp_verification.html')


def login_view(request):
    if request.method == "POST":
        mobile = request.POST.get('mobile', '').strip()
        role = request.POST.get('role', '').strip()

        if not is_valid_mobile(mobile):
            messages.error(request, 'Enter a valid 10-digit mobile number.')
            return render(request, 'kisan1/login.html')

        user_exists = UserRegistration.objects.filter(mobile=mobile, role=role).exists()
        if not user_exists:
            messages.error(request, "User not registered!")
            return render(request, 'kisan1/login.html')

        if not can_attempt_login(mobile, context='login'):
            messages.error(request, 'Too many failed login attempts. Please wait before trying again.')
            return render(request, 'kisan1/login.html')

        if not can_send_otp(mobile, context='login'):
            messages.error(request, 'Too many OTP requests. Please wait a few minutes and try again.')
            return render(request, 'kisan1/login.html')

        # 4-digit OTP
        otp_payload = create_otp_session_payload()
        request.session['login_otp'] = otp_payload
        request.session['mobile'] = mobile
        request.session['role'] = role
        _set_otp_back_target(request, 'login_otp_back_url')

        announce_otp(mobile, otp_payload['code'], context='login')
        if is_debug_mode():
            logger.info('LOGIN OTP for %s is %s', mobile, otp_payload['code'])
        send_real_otp_sms(mobile, otp_payload['code'])
        return redirect('verify_otp_login')

    return render(request, 'kisan1/login.html')


def otp_view(request):
    attempts = int(request.session.get('login_otp_attempts', 0))
    if attempts >= 5:
        request.session.pop('login_otp', None)
        request.session.pop('login_otp_attempts', None)
        messages.error(request, 'Too many invalid OTP attempts. Please login again to generate a new OTP.')
        return redirect('login')

    if request.method == "POST":
        if is_otp_valid(request.session.get('login_otp'), request.POST.get('otp')):
            mobile = request.session.get('mobile')
            role = request.session.get('role')

            user = get_object_or_404(UserRegistration, mobile=mobile, role=role)

            request.session['user_id'] = user.id
            request.session['name'] = user.name
            request.session['otp_verified'] = True
            request.session['active_role'] = role
            request.session['role_group'] = _assign_group_for_role(role).name

            if 'login_otp' in request.session:
                del request.session['login_otp']
            request.session.pop('login_otp_attempts', None)
            request.session.pop('login_otp_back_url', None)
            clear_login_attempts(mobile, context='login')

            messages.success(request, f"Welcome back, {user.name}!")

            if role == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=role)

        updated_attempts = attempts + 1
        request.session['login_otp_attempts'] = updated_attempts
        mobile = request.session.get('mobile')
        if mobile:
            register_failed_login_attempt(mobile, context='login')
        if updated_attempts >= 5:
            request.session.pop('login_otp', None)
            request.session.pop('login_otp_attempts', None)
            messages.error(request, 'Too many invalid OTP attempts. Please login again to generate a new OTP.')
            return redirect('login')
        messages.error(request, "Invalid OTP")

    return render(request, 'kisan1/otp_verify.html')
