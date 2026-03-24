import re
import logging
from kisan1.views.shared import send_otp
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from kisan1.models import (
    FarmerProfile,
    LaborProfile,
    Location,
    LeaseProfile,
    PesticideProfile,
    ToolInventory,
    ToolsProfile,
    TractorProfile,
    UserIdentity,
    UserRegistration,
)
from kisan1.views.shared import (
    can_attempt_login,
    check_login,
    can_send_otp,
    clear_login_attempts,
    create_otp_session_payload,
    get_otp_remaining_seconds,
    is_debug_mode,
    is_otp_expired,
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
OTP_ATTEMPT_LIMIT = getattr(settings, 'OTP_ATTEMPT_LIMIT', 5)
MINIMUM_WORKING_AGE = 18
MAX_REGISTRATION_AGE = 100
EXPERIENCE_FIELD_LABELS = {
    'experience': _('Total experience'),
    'since_years': _('Business experience'),
    'exp_Ploughing': _('Ploughing experience'),
    'exp_Harrowing': _('Harrowing experience'),
    'exp_Transport': _('Transport experience'),
    'exp_Harvesting': _('Harvesting experience'),
    'exp_Sowing': _('Sowing experience'),
}
REGISTRATION_ROUTE_NAMES = {
    'farmer': 'farmer_register',
    'tractor': 'tractor_register',
    'labor': 'labor_register',
    'lease': 'lease_register',
    'tools': 'tools_register',
    'pesticide': 'register_pesticide',
}


def _assign_group_for_role(role):
    group, _ = Group.objects.get_or_create(name=f'role_{role}')
    return group


def welcome(request):
    return render(request, 'kisan1/welcome.html', {'show_language_selector': True})


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


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_common_registration_fields(request, template_name, *, name, mobile):
    age_raw = (request.POST.get('age') or '').strip()
    pincode = (request.POST.get('pincode') or '').strip()
    state = (request.POST.get('state') or '').strip()
    district = (request.POST.get('district') or '').strip()
    mandal = (request.POST.get('mandal') or '').strip()
    village = (request.POST.get('village') or '').strip()

    if not name or not mobile or not age_raw or not pincode or not state or not district or not mandal or not village:
        messages.error(request, _("Please fill in all required fields before continuing."))
        return render(request, template_name)

    if not _is_positive_int(age_raw, min_value=MINIMUM_WORKING_AGE, max_value=MAX_REGISTRATION_AGE):
        messages.error(
            request,
            _("Age must be between %(minimum_age)s and %(maximum_age)s.") % {
                'minimum_age': MINIMUM_WORKING_AGE,
                'maximum_age': MAX_REGISTRATION_AGE,
            },
        )
        return render(request, template_name)

    return None


def _validate_experience_years(request, template_name):
    age = _parse_int((request.POST.get('age') or '').strip())
    if age is None:
        return render(request, template_name)

    max_experience = max(0, age - MINIMUM_WORKING_AGE)
    for field_name, label in EXPERIENCE_FIELD_LABELS.items():
        raw_value = (request.POST.get(field_name) or '').strip()
        if not raw_value:
            continue
        if not _is_positive_int(raw_value, min_value=0, max_value=max_experience):
            messages.error(
                request,
                _("%(field)s must be less than or equal to %(limit)s years because minimum working age is %(minimum_age)s.") % {
                    'field': label,
                    'limit': max_experience,
                    'minimum_age': MINIMUM_WORKING_AGE,
                },
            )
            return render(request, template_name)
    return None


def _set_otp_back_target(request, session_key):
    request.session[session_key] = request.path


def _render_registration(request, template_name, context=None):
    base_context = {'show_language_selector': False}
    if context:
        base_context.update(context)
    return render(request, template_name, base_context)


def _clear_registration_session(request):
    for key in ('reg_otp', 'reg_core', 'reg_profile', 'reg_otp_attempts', 'otp_back_url'):
        request.session.pop(key, None)


def _existing_registration_for_role(mobile, role):
    return UserRegistration.objects.filter(mobile=mobile, role=role).first()


def _redirect_existing_registration(request, role):
    _clear_registration_session(request)
    messages.warning(request, _("This user has been registered."))
    return redirect(REGISTRATION_ROUTE_NAMES.get(role, 'register_choice'))


def otp_back(request):
    target = request.session.get('otp_back_url') or request.session.get('login_otp_back_url')
    unsafe_targets = {'/verify-otp/', '/verify-otp-login/', request.path}
    if not target or target in unsafe_targets:
        return redirect('register_choice')
    return redirect(target)

def handle_registration(request, role, template_name):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        mobile = request.POST.get('mobile', '').strip()

        if not name or not mobile:
            messages.error(request, _("All fields are required!"))
            return _render_registration(request, template_name)

        if not is_valid_name(name):
            messages.error(request, _("Name should contain only letters and spaces (minimum 3 characters)."))
            return _render_registration(request, template_name)

        if not is_valid_mobile(mobile):
            messages.error(request, _("Enter a valid 10-digit mobile number."))
            return _render_registration(request, template_name)

        if _existing_registration_for_role(mobile, role):
            messages.warning(request, _("This user has been registered."))
            return _render_registration(request, template_name)

        invalid_common_response = _validate_common_registration_fields(
            request,
            template_name,
            name=name,
            mobile=mobile,
        )
        if invalid_common_response:
            return invalid_common_response
        invalid_experience_response = _validate_experience_years(request, template_name)
        if invalid_experience_response:
            return invalid_experience_response

        age = _parse_int((request.POST.get('age') or '').strip())

        core_data = {
            'name': name,
            'age': age,
            'mobile': mobile,
            'role': role,
            'pincode': request.POST.get('pincode'),
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
                messages.error(request, _("Enter a valid farmer passbook number (T followed by 11 digits)."))
                return _render_registration(request, template_name)
            profile_data = {
                'gender': gender,
                'passbook_number': passbook,
            }
        elif role == 'tractor':
            selected_services = request.POST.getlist('services')
            if not selected_services:
                messages.error(request, _("Please select at least one service."))
                return _render_registration(request, template_name)
                
            services_list = []
            for service in selected_services:
                exp = (request.POST.get(f'exp_{service}') or '').strip()
                wage = (request.POST.get(f'wage_{service}') or '').strip()
                if not exp or not wage:
                    messages.error(request, _("Please provide both experience and hourly rate for every selected tractor service."))
                    return _render_registration(request, template_name)
                services_list.append(f"{service} ({exp} Yrs @ Rs. {wage}/hr)")

            driving_license = (request.POST.get('driving_license') or '').strip()
            base_wage = (request.POST.get('base_wage') or '').strip()
            experience = (request.POST.get('experience') or '').strip()
            if (
                not driving_license
                or not TRACTOR_LICENSE_RE.fullmatch(driving_license.upper())
                or not _is_positive_int(base_wage, min_value=1)
                or not _is_positive_int(experience, min_value=0, max_value=100)
            ):
                messages.error(request, _("Please provide valid tractor registration details."))
                return _render_registration(request, template_name)

            profile_data = {
                'experience': experience,
                'wage_amount': base_wage,
                'driving_license': driving_license,
                'services': " | ".join(services_list),
                'gender': 'Not Specified',
            }
        elif role == 'labor':
            selected_skills = request.POST.getlist('skills')
            if not selected_skills:
                messages.error(request, _("Please select at least one skill."))
                return _render_registration(request, template_name)
                
            skills_with_exp = []
            for skill in selected_skills:
                exp = (request.POST.get(f'exp_{skill}') or '').strip()
                if not exp:
                    messages.error(request, _("Please provide experience for every selected skill."))
                    return _render_registration(request, template_name)
                skills_with_exp.append(f"{skill} ({exp} Yrs)")

            gender = (request.POST.get('gender') or '').strip()
            wage_amount = (request.POST.get('wage_amount') or '').strip()
            wage_type = (request.POST.get('wage_type') or '').strip()
            if not gender or not wage_type or not _is_positive_int(wage_amount, min_value=1):
                messages.error(request, _("Please provide valid labor registration details."))
                return _render_registration(request, template_name)

            profile_data = {
                'skills': ", ".join(skills_with_exp),
                'gender': gender,
                'wage_amount': wage_amount,
                'wage_type': wage_type,
            }
        elif role == 'lease':
            selected_soils = request.POST.getlist('soils')
            if not selected_soils:
                messages.error(request, _("Please select at least one soil type."))
                return _render_registration(request, template_name)
                
            soil_details_list = []
            for soil in selected_soils:
                acres = request.POST.get(f'acres_{soil}')
                cost = request.POST.get(f'cost_{soil}')
                if acres and cost:
                    soil_details_list.append(f"{soil.replace('_', ' ')} ({acres} Acres @ Rs. {cost}/acre)")
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
                messages.error(request, _("Please provide valid lease registration details."))
                return _render_registration(request, template_name)

            profile_data = {
                'total_land': total_land,
                'water_facility': water_resource,
                'soil_type': " | ".join(soil_details_list),
                'passbook_number': passbook,
                'lease_per_day': 0,
            }
        elif role == 'tools':
            selected_tools = request.POST.getlist('tools')
            if not selected_tools:
                messages.error(request, _("Please select at least one tool."))
                return _render_registration(request, template_name)
                
            tools_with_cost = []
            tool_inventory = []
            for tool in selected_tools:
                cost = (request.POST.get(f'cost_{tool}') or '').strip()
                if cost and _is_positive_int(cost, min_value=1):
                    tools_with_cost.append(f"{tool} (Rs. {cost}/hr)")
                    tool_inventory.append({
                        'tool_name': tool,
                        'rate': int(cost),
                        'rate_unit': 'hr',
                    })
                else:
                    messages.error(request, _("Please provide a valid hourly rent for every selected tool."))
                    return _render_registration(request, template_name)

            shop_name = (request.POST.get('shop_name') or '').strip()
            if not shop_name:
                messages.error(request, _("Shop name is required for tools registration."))
                return _render_registration(request, template_name)

            profile_data = {
                'shop_name': shop_name,
                'tools_type': " | ".join(tools_with_cost),
                'rent_per_hour': 0,
                'tool_inventory': tool_inventory,
            }
        elif role == 'pesticide':
            selected_products = request.POST.getlist('products')
            if not selected_products:
                messages.error(request, _("Please select at least one product."))
                return _render_registration(request, template_name)
                
            shop_name = (request.POST.get('shop_name') or '').strip()
            license_id = (request.POST.get('license_id') or '').strip()
            since_years = (request.POST.get('since_years') or '').strip()
            if (
                not shop_name
                or not license_id
                or not PFS_LICENSE_RE.fullmatch(license_id.upper())
                or not _is_positive_int(since_years, min_value=0, max_value=100)
            ):
                messages.error(request, _("Please provide valid fertilizer shop registration details."))
                return _render_registration(request, template_name)

            profile_data = {
                'shop_name': shop_name,
                'license_id': license_id,
                'since_years': since_years,
                'products_sold': " | ".join(selected_products),
            }

        request.session['reg_core'] = core_data
        request.session['reg_profile'] = profile_data

        if not can_send_otp(mobile, context='registration'):
            messages.error(request, _('Too many OTP requests. Please wait a few minutes and try again.'))
            return _render_registration(request, template_name)

        request.session.pop('login_otp_attempts', None)

        # 4-digit OTP
        otp_code, otp_payload = create_otp_session_payload()
        request.session['reg_otp'] = otp_payload
        _set_otp_back_target(request, 'otp_back_url')

        announce_otp(mobile, otp_code, context='registration')

        if is_debug_mode():
            logger.info('REGISTRATION OTP for %s is %s', mobile, otp_code)

        send_real_otp_sms(mobile, otp_code)
        return redirect('verify_otp')

    return _render_registration(request, template_name)


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
    attempts = int(request.session.get('reg_otp_attempts', 0))
    attempts_left = max(0, OTP_ATTEMPT_LIMIT - attempts)
    remaining_seconds = get_otp_remaining_seconds(otp_payload)

    if is_otp_expired(otp_payload):
        request.session.pop('reg_otp', None)
        request.session.pop('reg_otp_attempts', None)
        messages.error(request, _('OTP has expired. Please register again to generate a new OTP.'), extra_tags='otp')
        return render(request, 'kisan1/otp_verification.html', {
            'otp_attempts_left': OTP_ATTEMPT_LIMIT,
            'otp_remaining_seconds': 0,
            'otp_expired': True,
        })

    if attempts >= OTP_ATTEMPT_LIMIT:
        request.session.pop('reg_otp', None)
        request.session.pop('reg_otp_attempts', None)
        messages.error(request, _('Too many invalid OTP attempts. Please register again to generate a new OTP.'), extra_tags='otp')
        return redirect('register_choice')

    if request.method == 'POST':
        if is_otp_expired(otp_payload):
            request.session.pop('reg_otp', None)
            request.session.pop('reg_otp_attempts', None)
            messages.error(request, _('OTP has expired. Please register again to generate a new OTP.'), extra_tags='otp')
            return render(request, 'kisan1/otp_verification.html', {
                'otp_attempts_left': OTP_ATTEMPT_LIMIT,
                'otp_remaining_seconds': 0,
                'otp_expired': True,
            })

        if is_otp_valid(otp_payload, request.POST.get('otp')):
            core = request.session.get('reg_core')
            prof = request.session.get('reg_profile')

            if not core or not prof:
                _clear_registration_session(request)
                messages.error(request, _('Registration session is incomplete. Please register again.'))
                return redirect('register_choice')

            if _existing_registration_for_role(core['mobile'], core['role']):
                return _redirect_existing_registration(request, core['role'])

            identity, identity_created = UserIdentity.objects.get_or_create(mobile=core['mobile'])
            defaults = dict(core)
            defaults['identity'] = identity
            try:
                user = UserRegistration.objects.create(**defaults)
            except IntegrityError:
                return _redirect_existing_registration(request, core['role'])

            location_obj, location_created = Location.objects.get_or_create(
                pincode=core.get('pincode') or '',
                district=core.get('district') or '',
                mandal=core.get('mandal') or '',
                village=core.get('village') or '',
            )
            user.location = location_obj
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
                tool_defaults = dict(prof)
                tool_inventory = tool_defaults.pop('tool_inventory', [])
                ToolsProfile.objects.get_or_create(user=user, defaults=tool_defaults)
                for item in tool_inventory:
                    ToolInventory.objects.update_or_create(
                        owner=user,
                        tool_name=item['tool_name'],
                        defaults={
                            'rate': item['rate'],
                            'rate_unit': item.get('rate_unit', 'hr'),
                            'is_available': True,
                        },
                    )
            elif core['role'] == 'pesticide':
                PesticideProfile.objects.get_or_create(user=user, defaults=prof)

            request.session['mobile'] = user.mobile
            request.session['role'] = core['role']
            request.session['otp_verified'] = True
            request.session['user_id'] = user.id
            request.session['role_group'] = django_group.name
            _clear_registration_session(request)

            if core['role'] == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=core['role'])

        updated_attempts = attempts + 1
        request.session['reg_otp_attempts'] = updated_attempts
        attempts_left = max(0, OTP_ATTEMPT_LIMIT - updated_attempts)
        if updated_attempts >= OTP_ATTEMPT_LIMIT:
            request.session.pop('reg_otp', None)
            request.session.pop('reg_otp_attempts', None)
            messages.error(request, _('Too many invalid OTP attempts. Please register again to generate a new OTP.'), extra_tags='otp')
            return redirect('register_choice')
        messages.error(request, _("Invalid OTP"), extra_tags='otp')

    return render(request, 'kisan1/otp_verification.html', {
        'otp_attempts_left': attempts_left,
        'otp_remaining_seconds': remaining_seconds,
    })


def login_view(request):
    # ❌ REMOVE / COMMENT THIS BLOCK
    # if check_login(request):
    #     role = request.session.get('active_role') or request.session.get('role')
    #     if role == 'farmer':
    #         return redirect('main_home')
    #     if role:
    #         return redirect('dashboard', role=role)

    if request.method == "POST":
        mobile = request.POST.get('mobile', '').strip()
        role = request.POST.get('role', '').strip()

        if not is_valid_mobile(mobile):
            messages.error(request, _('Enter a valid 10-digit mobile number.'), extra_tags='login')
            return render(request, 'kisan1/login.html')

        user_exists = UserRegistration.objects.filter(mobile=mobile, role=role).exists()
        if not user_exists:
            messages.error(request, _("User not registered!"), extra_tags='login')
            return render(request, 'kisan1/login.html')

        if not can_attempt_login(mobile, context='login'):
            messages.error(request, _('Too many failed login attempts. Please wait before trying again.'), extra_tags='login')
            return render(request, 'kisan1/login.html')

        if not can_send_otp(mobile, context='login'):
            messages.error(request, _('Too many OTP requests. Please wait a few minutes and try again.'), extra_tags='login')
            return render(request, 'kisan1/login.html')

        request.session.pop('login_otp_attempts', None)

        # 4-digit OTP
        otp_code, otp_payload = create_otp_session_payload()
        request.session['login_otp'] = otp_payload
        request.session['mobile'] = mobile
        request.session['role'] = role
        _set_otp_back_target(request, 'login_otp_back_url')

        announce_otp(mobile, otp_code, context='login')
        if is_debug_mode():
            logger.info('LOGIN OTP for %s is %s', mobile, otp_code)
        send_real_otp_sms(mobile, otp_code)
        return redirect('verify_otp_login')

    return render(request, 'kisan1/login.html')

def otp_view(request):
    otp_payload = request.session.get('login_otp')
    attempts = int(request.session.get('login_otp_attempts', 0))
    attempts_left = max(0, OTP_ATTEMPT_LIMIT - attempts)
    remaining_seconds = get_otp_remaining_seconds(otp_payload)

    if is_otp_expired(otp_payload):
        request.session.pop('login_otp', None)
        request.session.pop('login_otp_attempts', None)
        messages.error(request, _('OTP has expired. Please login again to generate a new OTP.'), extra_tags='otp')
        return render(request, 'kisan1/otp_verify.html', {
            'otp_attempts_left': OTP_ATTEMPT_LIMIT,
            'otp_remaining_seconds': 0,
            'otp_expired': True,
        })

    if attempts >= OTP_ATTEMPT_LIMIT:
        request.session.pop('login_otp', None)
        request.session.pop('login_otp_attempts', None)
        messages.error(request, _('Too many invalid OTP attempts. Please login again to generate a new OTP.'), extra_tags='login')
        return redirect('login')

    if request.method == "POST":
        if is_otp_expired(otp_payload):
            request.session.pop('login_otp', None)
            request.session.pop('login_otp_attempts', None)
            messages.error(request, _('OTP has expired. Please login again to generate a new OTP.'), extra_tags='otp')
            return render(request, 'kisan1/otp_verify.html', {
                'otp_attempts_left': OTP_ATTEMPT_LIMIT,
                'otp_remaining_seconds': 0,
                'otp_expired': True,
            })

        if is_otp_valid(otp_payload, request.POST.get('otp')):
            mobile = request.session.get('mobile')
            role = request.session.get('role')

            user = get_object_or_404(UserRegistration, mobile=mobile, role=role)
            if user.identity_id is None and mobile:
                identity, identity_created = UserIdentity.objects.get_or_create(mobile=mobile)
                user.identity = identity
                user.save(update_fields=['identity'])

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

            if role == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=role)

        updated_attempts = attempts + 1
        request.session['login_otp_attempts'] = updated_attempts
        attempts_left = max(0, OTP_ATTEMPT_LIMIT - updated_attempts)
        mobile = request.session.get('mobile')
        if mobile:
            register_failed_login_attempt(mobile, context='login')
        if updated_attempts >= OTP_ATTEMPT_LIMIT:
            request.session.pop('login_otp', None)
            request.session.pop('login_otp_attempts', None)
            messages.error(request, _('Too many invalid OTP attempts. Please login again to generate a new OTP.'), extra_tags='login')
            return redirect('login')
        messages.error(request, _("Invalid OTP"), extra_tags='otp')

    return render(request, 'kisan1/otp_verify.html', {
        'otp_attempts_left': attempts_left,
        'otp_remaining_seconds': remaining_seconds,
    })
