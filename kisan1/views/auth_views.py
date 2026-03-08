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
            profile_data = {
                'gender': request.POST.get('gender'),
                'passbook_number': request.POST.get('passbook'),
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

            profile_data = {
                'experience': request.POST.get('experience') or 0,
                'wage_amount': request.POST.get('base_wage') or 0,
                'driving_license': request.POST.get('driving_license'),
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

            profile_data = {
                'skills': ", ".join(skills_with_exp),
                'gender': request.POST.get('gender'),
                'wage_amount': request.POST.get('wage_amount') or 0,
                'wage_type': request.POST.get('wage_type'),
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

            profile_data = {
                'total_land': request.POST.get('total_land') or 0.0,
                'water_facility': request.POST.get('water_resource'),
                'soil_type': " | ".join(soil_details_list),
                'passbook_number': request.POST.get('passbook'),
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

            profile_data = {
                'shop_name': request.POST.get('shop_name') or "Individual Owner",
                'tools_type': " | ".join(tools_with_cost),
                'rent_per_hour': 0,
            }
        elif role == 'pesticide':
            selected_products = request.POST.getlist('products')
            # NEW: Stop if no products selected
            if not selected_products:
                messages.error(request, "Please select at least one product.")
                return render(request, template_name)
                
            profile_data = {
                'shop_name': request.POST.get('shop_name'),
                'license_id': request.POST.get('license_id'),
                'since_years': request.POST.get('since_years') or 0,
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
        messages.error(request, 'Too many invalid OTP attempts. Please register again.')
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

            if core['role'] == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=core['role'])

        request.session['reg_otp_attempts'] = attempts + 1
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

        announce_otp(mobile, otp_payload['code'], context='login')
        if is_debug_mode():
            logger.info('LOGIN OTP for %s is %s', mobile, otp_payload['code'])
        send_real_otp_sms(mobile, otp_payload['code'])
        return redirect('verify_otp_login')

    return render(request, 'kisan1/login.html')


def otp_view(request):
    attempts = int(request.session.get('login_otp_attempts', 0))
    if attempts >= 5:
        messages.error(request, 'Too many invalid OTP attempts. Please login again.')
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
            clear_login_attempts(mobile, context='login')

            messages.success(request, f"Welcome back, {user.name}!")

            if role == 'farmer':
                return redirect('main_home')
            return redirect('dashboard', role=role)

        request.session['login_otp_attempts'] = attempts + 1
        mobile = request.session.get('mobile')
        if mobile:
            register_failed_login_attempt(mobile, context='login')
        messages.error(request, "Invalid OTP")

    return render(request, 'kisan1/otp_verify.html')
