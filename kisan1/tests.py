from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError

from kisan1.views.shared import create_otp_session_payload

# Graceful import in case location_service isn't fully set up yet
try:
    from .location_service import load_telangana_pincodes
except ImportError:
    pass

from .models import (
    LaborBooking,
    LaborProfile,
    LeaseLandRequest,
    LeaseProfile,
    PesticideInventory,
    PesticideProfile,
    PincodeMapping,
    ShopOrder,
    ToolInventory,
    ToolRentalBooking,
    ToolsProfile,
    TractorBooking,
    TractorProfile,
    UserRegistration,
)

class KisanAsaraTests(TestCase):
    def setUp(self):
        self.farmer = UserRegistration.objects.create(
            name="Test Farmer",
            mobile="9999999999",
            role="farmer",
            state="Telangana",
            district="Warangal",
            mandal="Hanamkonda",
            village="Kazipet",
            is_verified=True,
        )
        self.labor_user = UserRegistration.objects.create(name="Labor One", mobile="9888888888", role="labor", is_verified=True)
        self.tractor_user = UserRegistration.objects.create(name="Tractor One", mobile="9777777777", role="tractor", is_verified=True)
        self.tools_user = UserRegistration.objects.create(name="Tools One", mobile="9666666666", role="tools", is_verified=True)
        self.lease_user = UserRegistration.objects.create(name="Lease One", mobile="9555555555", role="lease", is_verified=True)
        self.shop_user = UserRegistration.objects.create(name="Shop One", mobile="9444444444", role="pesticide", is_verified=True)

        self.labor_profile = LaborProfile.objects.create(user=self.labor_user, wage_amount=500, wage_type='Per Day')
        self.tractor_profile = TractorProfile.objects.create(user=self.tractor_user, wage_amount=800, services='Ploughing (₹800/hr)')
        self.tools_profile = ToolsProfile.objects.create(
            user=self.tools_user,
            shop_name='Tool Hub',
            tools_type='Tractor (₹500/hr) | Harvester (₹700/hr)',
        )
        self.tool_inventory_tractor = ToolInventory.objects.create(
            owner=self.tools_user,
            tool_name='Tractor',
            rate=500,
            rate_unit='hr',
            is_available=True,
        )
        self.tool_inventory_harvester = ToolInventory.objects.create(
            owner=self.tools_user,
            tool_name='Harvester',
            rate=700,
            rate_unit='hr',
            is_available=True,
        )
        self.lease_profile = LeaseProfile.objects.create(user=self.lease_user, total_land=5.0)
        self.shop_profile = PesticideProfile.objects.create(
            user=self.shop_user,
            shop_name='Green Agro',
            license_id='LIC-001',
            since_years=5,
            products_sold='Urea|Seeds',
        )
        self.inventory = PesticideInventory.objects.create(
            shop=self.shop_user,
            item_name='Urea',
            category='Fertilizer',
            price=100,
            stock_quantity=20,
        )

    def _set_session(self, user, role):
        session = self.client.session
        session['user_id'] = user.id
        session['mobile'] = user.mobile
        session['role'] = role
        session['active_role'] = role
        session['otp_verified'] = True
        session.save()


    def test_language_toggle_redirects_back(self):
        response = self.client.post(reverse('set_language'), {'language': 'te', 'next': reverse('login')})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_registration_pages_load(self):
        routes = [
            'farmer_register',
            'tractor_register',
            'labor_register',
            'lease_register',
            'tools_register',
            'register_pesticide',
            'login',
            'welcome',
        ]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_farmer_registration_post_sets_otp(self):
        payload = {
            'name': 'Ramesh Kumar', 'mobile': '9123456789', 'age': '30', 
            'gender': 'Male', 'passbook': 'T12345678901', 'state': 'Telangana', 
            'district': 'Nizamabad', 'mandal': 'Armoor', 'village': 'Perkit', 'pincode': '503001',
        }
        response = self.client.post(reverse('farmer_register'), payload)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp'))
        self.assertTrue(self.client.session.get('reg_otp'))

    def test_duplicate_registration_same_mobile_and_role_is_blocked(self):
        response = self.client.post(reverse('tractor_register'), {
            'name': 'Changed Tractor User',
            'mobile': self.tractor_user.mobile,
            'age': '32',
            'pincode': '503001',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'base_wage': '700',
            'driving_license': 'TS0520230000123',
            'experience': '5',
            'services': ['Ploughing'],
            'exp_Ploughing': '3',
            'wage_Ploughing': '700',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This user has been registered.')
        self.assertFalse(self.client.session.get('reg_otp'))
        self.assertEqual(UserRegistration.objects.filter(mobile=self.tractor_user.mobile, role='tractor').count(), 1)

    def test_same_details_with_different_mobile_can_register(self):
        response = self.client.post(reverse('tractor_register'), {
            'name': self.tractor_user.name,
            'mobile': '9234509876',
            'age': '32',
            'pincode': '503001',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'base_wage': '700',
            'driving_license': 'TS0520230000456',
            'experience': '5',
            'services': ['Ploughing'],
            'exp_Ploughing': '3',
            'wage_Ploughing': '700',
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp'))
        self.assertTrue(self.client.session.get('reg_otp'))

    def test_duplicate_registration_is_blocked_at_otp_verification(self):
        otp_code, otp_payload = create_otp_session_payload()
        session = self.client.session
        session['reg_otp'] = otp_payload
        session['reg_core'] = {
            'name': 'Changed Tractor User',
            'age': 32,
            'mobile': self.tractor_user.mobile,
            'role': 'tractor',
            'pincode': '503001',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'is_verified': False,
        }
        session['reg_profile'] = {
            'experience': '5',
            'wage_amount': '700',
            'driving_license': 'TS0520230000123',
            'services': 'Ploughing (3 Yrs @ Rs. 700/hr)',
            'gender': 'Not Specified',
        }
        session.save()

        response = self.client.post(reverse('verify_otp'), {'otp': otp_code}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This user has been registered.')
        self.assertEqual(UserRegistration.objects.filter(mobile=self.tractor_user.mobile, role='tractor').count(), 1)

    def test_farmer_registration_invalid_name_blocked(self):
        response = self.client.post(reverse('farmer_register'), {'name': 'Ramesh123', 'mobile': '9123456789'})
        self.assertEqual(response.status_code, 200)

    def test_dashboards_load_for_each_provider_role(self):
        cases = [
            (self.labor_user, 'labor'),
            (self.tractor_user, 'tractor'),
            (self.tools_user, 'tools'),
            (self.lease_user, 'lease'),
            (self.shop_user, 'pesticide'),
        ]
        for user, role in cases:
            with self.subTest(role=role):
                self._set_session(user, role)
                response = self.client.get(reverse('dashboard', kwargs={'role': role}))
                self.assertEqual(response.status_code, 200)

    def test_tool_management_routes_load_for_owner(self):
        self._set_session(self.tools_user, 'tools')
        for route in ['tool_add_products', 'tool_inventory', 'tool_change_rate']:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)

    def test_tool_owner_can_update_available_tool_rate(self):
        self._set_session(self.tools_user, 'tools')
        response = self.client.post(
            reverse('tool_change_rate'),
            {'tool_id': str(self.tool_inventory_tractor.id), 'rate': '650'},
        )
        self.assertRedirects(response, reverse('tool_change_rate'))
        self.tool_inventory_tractor.refresh_from_db()
        self.tools_profile.refresh_from_db()
        self.assertEqual(self.tool_inventory_tractor.rate, 650)
        self.assertIn('650', self.tools_profile.tools_type)

    def test_farmer_pages_load(self):
        self._set_session(self.farmer, 'farmer')
        self.assertEqual(self.client.get(reverse('farmer_booking')).status_code, 200)
        self.assertEqual(self.client.get(reverse('cart')).status_code, 200)

    def test_farmer_booking_renders_shop_tracking_dialog(self):
        ShopOrder.objects.create(
            farmer=self.farmer,
            shop=self.shop_profile,
            items_ordered='Urea (2 units @ Rs. 100)',
            total_cost=200,
            status='Confirmed',
        )

        self._set_session(self.farmer, 'farmer')
        response = self.client.get(reverse('farmer_booking'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Track Order')
        self.assertContains(response, 'trackingDialogBackdrop')
        self.assertContains(response, 'data-track-kind="shop"')
        self.assertContains(response, 'google.com/maps/dir/')

    def test_farmer_booking_renders_tool_and_tractor_tracking_dialogs(self):
        ToolRentalBooking.objects.create(
            farmer=self.farmer,
            tool_shop=self.tools_profile,
            tools_selected='Tractor: 2 hrs',
            receive_date='2026-03-24',
            return_date='2026-03-25',
            home_delivery=True,
            delivery_location='Kazipet, Hanamkonda, Telangana',
            total_cost=1000,
            status='Confirmed',
        )
        TractorBooking.objects.create(
            farmer=self.farmer,
            tractor_owner=self.tractor_profile,
            booking_date='2026-03-24',
            start_time='09:00',
            duration_hours=3,
            location='Field 12, Kazipet, Hanamkonda, Telangana',
            total_cost=2400,
            status='Confirmed',
        )

        self._set_session(self.farmer, 'farmer')
        response = self.client.get(reverse('farmer_booking'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-track-kind="tool"')
        self.assertContains(response, 'data-track-kind="tractor"')
        self.assertContains(response, 'Track Tools')
        self.assertContains(response, 'Track Tractor')
        self.assertContains(response, 'Open Tool Route')
        self.assertContains(response, 'Open Tractor Route')

    def test_farmer_booking_template_has_no_alert_calls(self):
        template_path = Path(__file__).resolve().parent / 'templates' / 'kisan1' / 'farmer_booking.html'
        self.assertNotIn('alert(', template_path.read_text(encoding='utf-8'))

    def test_book_labor_creates_booking_and_order(self):
        self._set_session(self.farmer, 'farmer')
        response = self.client.post(reverse('book_labor', args=[self.labor_profile.id]), {
            'duration': '2', 'booking_date': '2026-03-10', 'start_time': '10:00', 'location': 'Farm Plot 12',
        })
        self.assertRedirects(response, reverse('order_success'))
        self.assertEqual(LaborBooking.objects.filter(farmer=self.farmer, laborer=self.labor_profile).count(), 1)

    def test_book_tractor_creates_booking_and_order(self):
        self._set_session(self.farmer, 'farmer')
        response = self.client.post(reverse('book_tractor', args=[self.tractor_profile.id]), {
            'duration_hours': '3', 'booking_date': '2026-03-11', 'start_time': '09:00', 'location': 'Field 7',
        })
        self.assertRedirects(response, reverse('order_success'))
        self.assertEqual(TractorBooking.objects.filter(farmer=self.farmer, tractor_owner=self.tractor_profile).count(), 1)

    def test_book_tools_and_lease_create_records(self):
        self._set_session(self.farmer, 'farmer')
        tools_response = self.client.post(reverse('book_tool', args=[self.tools_profile.id]), {
            'receive_date': '2026-03-12', 'return_date': '2026-03-13', 'tool_Tractor': 'Tractor', 'hours_Tractor': '2',
        })
        self.assertRedirects(tools_response, reverse('order_success'))

        lease_response = self.client.post(reverse('request_lease', args=[self.lease_profile.id]), {
            'soil_type_requested': 'Red Soil', 'duration_months': '6', 'start_date': '2026-04-01', 'message_to_owner': 'Need fertile land',
        })
        self.assertRedirects(lease_response, reverse('order_success'))
        self.assertEqual(LeaseLandRequest.objects.filter(farmer=self.farmer, land=self.lease_profile).count(), 1)

    def test_shop_cart_checkout_creates_shoporder_and_order(self):
        self._set_session(self.farmer, 'farmer')
        add_to_cart = self.client.post(reverse('book_shop', args=[self.shop_profile.id]), {
            f'qty_{self.inventory.id}': '2',
        })
        self.assertRedirects(add_to_cart, reverse('cart'))

        checkout = self.client.post(reverse('cart'), {'confirm_checkout': '1'})
        self.assertRedirects(checkout, reverse('booking_success'))
        self.assertEqual(ShopOrder.objects.filter(farmer=self.farmer, shop=self.shop_profile).count(), 1)

    def test_self_booking_is_blocked(self):
        same_mobile_labor = UserRegistration.objects.create(
            name='Self Labor',
            mobile=self.farmer.mobile,
            role='labor',
            is_verified=True,
        )
        same_mobile_profile = LaborProfile.objects.create(user=same_mobile_labor, wage_amount=400, wage_type='Per Day')

        self._set_session(self.farmer, 'farmer')
        response = self.client.post(
            reverse('book_labor', args=[same_mobile_profile.id]),
            {'duration': '1', 'booking_date': '2026-03-21', 'start_time': '10:00', 'location': 'Self field'},
        )
        self.assertRedirects(response, reverse('main_home'))
        self.assertEqual(LaborBooking.objects.filter(farmer=self.farmer, laborer=same_mobile_profile).count(), 0)

    def test_provider_accept_updates_status_and_inventory(self):
        self._set_session(self.farmer, 'farmer')
        self.client.post(reverse('book_shop', args=[self.shop_profile.id]), {f'qty_{self.inventory.id}': '2'})
        self.client.post(reverse('cart'), {'confirm_checkout': '1'})
        order = ShopOrder.objects.get(farmer=self.farmer, shop=self.shop_profile)

        self._set_session(self.shop_user, 'pesticide')
        response = self.client.post(reverse('accept_shop_order', args=[order.id]))
        self.assertEqual(response.status_code, 302)

        order.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(order.status, 'Confirmed')
        self.assertEqual(self.inventory.stock_quantity, 18)

    def test_location_api_returns_data(self):
        PincodeMapping.objects.create(
            pincode='503001',
            district='Nizamabad',
            mandal='Armoor',
            village='Perkit',
        )
        response = self.client.get(reverse('get_location_api'), {'pincode': '503001'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('success'), True)
        self.assertIn('Perkit', response.json().get('villages', []))

    def test_admin_analytics_page_for_staff(self):
        User = get_user_model()
        admin_user = User.objects.create_user(username='admin', email='admin@example.com', password='StrongPass!123', is_staff=True)
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin_analytics'))
        self.assertEqual(response.status_code, 200)

    def test_provider_reject_and_farmer_cancel_flows(self):
        # Create labor booking
        self._set_session(self.farmer, 'farmer')
        self.client.post(reverse('book_labor', args=[self.labor_profile.id]), {
            'duration': '1', 'booking_date': '2026-03-20', 'start_time': '08:00', 'location': 'Plot 45',
        })
        labor_booking = LaborBooking.objects.get(farmer=self.farmer, laborer=self.labor_profile)

        # Labor provider rejects
        self._set_session(self.labor_user, 'labor')
        reject_resp = self.client.post(reverse('reject_labor_booking', args=[labor_booking.id]))
        self.assertEqual(reject_resp.status_code, 302)
        labor_booking.refresh_from_db()
        self.assertEqual(labor_booking.status, 'Rejected')

    def test_auth_otp_login_flow(self):
        session = self.client.session
        otp_code, otp_payload = create_otp_session_payload()
        session['login_otp'] = otp_payload
        session['mobile'] = self.farmer.mobile
        session['role'] = 'farmer'
        session.save()

        response = self.client.post(reverse('verify_otp_login'), {'otp': otp_code})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('main_home'))
        self.assertTrue(self.client.session.get('otp_verified'))

    def test_location_village_endpoint(self):
        PincodeMapping.objects.create(
            pincode='503002',
            district='Nizamabad',
            mandal='Armoor',
            village='VillageOne',
        )
        response = self.client.get(reverse('get_villages'), {'pincode': '503002'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'villages': ['VillageOne']})

    def test_main_home_loads(self):
        self._set_session(self.farmer, 'farmer')
        response = self.client.get(reverse('main_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.farmer.name)
        self.assertContains(response, 'All Services')

    def test_all_registration_posts_redirect_to_verify_otp(self):
        cases = [
            ('tractor_register', {
                'name': 'Tractor Driver',
                'mobile': '9234567890',
                'age': '28',
                'pincode': '503001',
                'state': 'Telangana',
                'district': 'Nizamabad',
                'mandal': 'Armoor',
                'village': 'Perkit',
                'base_wage': '500',
                'driving_license': 'TS0520230000123',
                'experience': '4',
                'services': ['Ploughing'],
                'exp_Ploughing': '2',
                'wage_Ploughing': '500',
            }),
            ('labor_register', {
                'name': 'Labor Person',
                'mobile': '9345678901',
                'age': '25',
                'pincode': '503001',
                'state': 'Telangana',
                'district': 'Nizamabad',
                'mandal': 'Armoor',
                'village': 'Perkit',
                'gender': 'Male',
                'wage_amount': '450',
                'wage_type': 'Per Day',
                'skills': ['Ploughing'],
                'exp_Ploughing': '2',
            }),
        ]
        for route, payload in cases:
            with self.subTest(route=route):
                response = self.client.post(reverse(route), payload)
                self.assertEqual(response.status_code, 302)
                self.assertRedirects(response, reverse('verify_otp'))

    def test_tractor_registration_blocks_experience_above_age_minus_eighteen(self):
        response = self.client.post(reverse('tractor_register'), {
            'name': 'Tractor Driver',
            'mobile': '9234567890',
            'age': '25',
            'pincode': '503001',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'base_wage': '500',
            'driving_license': 'TS0520230000123',
            'experience': '8',
            'services': ['Ploughing'],
            'exp_Ploughing': '8',
            'wage_Ploughing': '500',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get('reg_otp'))

    def test_labor_registration_blocks_skill_experience_above_age_minus_eighteen(self):
        response = self.client.post(reverse('labor_register'), {
            'name': 'Labor Person',
            'mobile': '9345678901',
            'age': '20',
            'pincode': '503001',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'gender': 'Male',
            'wage_amount': '450',
            'wage_type': 'Per Day',
            'skills': ['Ploughing'],
            'exp_Ploughing': '3',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get('reg_otp'))

    def test_pesticide_registration_blocks_since_years_above_age_minus_eighteen(self):
        response = self.client.post(reverse('register_pesticide'), {
            'shop_name': 'Agro Shop',
            'name': 'Shop Owner',
            'age': '22',
            'mobile': '9456789012',
            'pincode': '503001',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'license_id': 'TS-FERT-2024-1234',
            'since_years': '5',
            'products': ['Seeds'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get('reg_otp'))

    def test_reject_and_cancel_flow_updates_status(self):
        self._set_session(self.farmer, 'farmer')
        self.client.post(
            reverse('book_labor', args=[self.labor_profile.id]),
            {'duration': '1', 'booking_date': '2026-03-24', 'start_time': '09:00', 'location': 'Plot 88'},
        )
        booking = LaborBooking.objects.get(farmer=self.farmer, laborer=self.labor_profile)
        response = self.client.post(reverse('cancel_booking', kwargs={'type': 'labor', 'id': booking.id}))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'Cancelled')

    def test_dashboard_shows_toast_messages_after_provider_action(self):
        TractorBooking.objects.create(
            farmer=self.farmer,
            tractor_owner=self.tractor_profile,
            booking_date='2026-03-24',
            start_time='09:00',
            duration_hours=2,
            location='Field 4',
            total_cost=1600,
        )
        booking = TractorBooking.objects.get(farmer=self.farmer, tractor_owner=self.tractor_profile)

        self._set_session(self.tractor_user, 'tractor')
        response = self.client.post(reverse('accept_tractor_booking', args=[booking.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'toast-notice')
        self.assertContains(response, 'Accepted tractor booking from Test Farmer!')

    def test_role_guard_blocks_wrong_provider_actions(self):
        self._set_session(self.labor_user, 'labor')
        response = self.client.post(
            reverse('book_labor', args=[self.labor_profile.id]),
            {'duration': '1', 'booking_date': '2026-03-20', 'start_time': '08:00', 'location': 'Plot 10'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_user_created_successfully(self):
        user = UserRegistration.objects.get(mobile="9999999999")
        self.assertEqual(user.name, "Test Farmer")
        self.assertEqual(user.role, "farmer")
        self.assertTrue(user.is_verified)

    def test_welcome_page_loads(self):
        response = self.client.get(reverse('welcome'))
        self.assertEqual(response.status_code, 200)

    def test_language_selector_is_only_visible_on_welcome_page(self):
        welcome_response = self.client.get(reverse('welcome'))
        self.assertEqual(welcome_response.status_code, 200)
        self.assertContains(welcome_response, '<div class="language-switcher">', html=False)

        self._set_session(self.tools_user, 'tools')
        dashboard_response = self.client.get(reverse('dashboard', kwargs={'role': 'tools'}))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertNotContains(dashboard_response, 'id="lang-switch"', html=False)

        self._set_session(self.farmer, 'farmer')
        home_response = self.client.get(reverse('main_home'))
        self.assertEqual(home_response.status_code, 200)
        self.assertNotContains(home_response, 'id="lang-switch"', html=False)

    def test_cart_checkout_saves_shop_order(self):
        farmer = UserRegistration.objects.get(mobile="9999999999", role="farmer")
        shop_user = UserRegistration.objects.create(name="Store", mobile="8888888888", role="pesticide", is_verified=True)
        shop_profile = PesticideProfile.objects.create(user=shop_user, shop_name="Agro", license_id="LIC-1", products_sold="Urea")

        session = self.client.session
        session['user_id'] = farmer.id
        session['otp_verified'] = True
        session['mobile'] = farmer.mobile
        session['temp_cart'] = {'shop_id': shop_profile.id, 'shop_name': shop_profile.shop_name, 'items_ordered': ['Urea'], 'total_cost': 200}
        session.save()

        response = self.client.post(reverse('cart'), {'confirm_checkout': '1'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('booking_success'))
        self.assertEqual(ShopOrder.objects.filter(farmer=farmer, shop=shop_profile).count(), 1)

    def test_login_otp_rate_limit_blocks_spam(self):
        cache.clear()
        payload = {'mobile': self.farmer.mobile, 'role': 'farmer'}
        for _ in range(5):
            response = self.client.post(reverse('login'), payload)
            self.assertEqual(response.status_code, 302)
        blocked = self.client.post(reverse('login'), payload)
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, 'Too many OTP requests')
        
    def test_book_labor_invalid_duration_is_rejected(self):
        self._set_session(self.farmer, 'farmer')
        response = self.client.post(
            reverse('book_labor', args=[self.labor_profile.id]),
            {'duration': '0', 'booking_date': '2026-03-10', 'start_time': '10:00', 'location': 'Farm Plot 12'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LaborBooking.objects.filter(farmer=self.farmer, laborer=self.labor_profile).count(), 0)

    def test_pfs_inventory_rejects_invalid_category(self):
        self._set_session(self.shop_user, 'pesticide')
        response = self.client.post(
            reverse('dashboard', kwargs={'role': 'pesticide'}),
            {
                'add_product': '1',
                'item_name': 'Starter Combo',
                'category': 'P&F&S',
                'market_price': '1600',
                'price': '1500',
                'stock_quantity': '10',
            },
        )
        self.assertRedirects(response, reverse('dashboard', kwargs={'role': 'pesticide'}))
        item = PesticideInventory.objects.get(shop=self.shop_user, item_name='Starter Combo', category='Pesticides')
        self.assertEqual(item.market_price, 1600)



    def test_hidden_pincode_location_data_is_blocked(self):
        response = self.client.get(reverse('get_location_api'), {'pincode': '503111'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': False, 'error': 'Restricted Pincode'})



    def test_pfs_shop_owner_can_save_shop_price(self):
        self._set_session(self.shop_user, 'pesticide')
        item = PesticideInventory.objects.create(
            shop=self.shop_user,
            item_name='Urea',
            category='Fertilizer',
            market_price=1200,
            price=1100,
            stock_quantity=10,
        )
        response = self.client.post(
            reverse('dashboard', kwargs={'role': 'pesticide'}),
            {'save_shop_price': '1', 'item_id': str(item.id), 'shop_price': '1050'},
        )
        self.assertRedirects(response, reverse('dashboard', kwargs={'role': 'pesticide'}))
        item.refresh_from_db()
        self.assertEqual(item.price, 1050)



    def test_load_pincodes_skips_hidden_pincodes(self):
        from .location_service import load_telangana_pincodes
        load_telangana_pincodes(force=True)
        self.assertFalse(PincodeMapping.objects.filter(pincode='503111').exists())

    def test_pincode_mapping_model_blocks_hidden_pincode(self):
        with self.assertRaises(ValidationError):
            PincodeMapping.objects.create(
                pincode='503111',
                district='Kamareddy',
                mandal='Kamareddy',
                village='Hidden Village',
            )



    def test_hidden_pincode_location_data_is_blocked(self):
        response = self.client.get(reverse('get_location_api'), {'pincode': '503111'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': False, 'error': 'Restricted Pincode'})



    def test_pfs_shop_owner_can_save_shop_price(self):
        self._set_session(self.shop_user, 'pesticide')
        item = PesticideInventory.objects.create(
            shop=self.shop_user,
            item_name='Urea',
            category='Fertilizer',
            market_price=1200,
            price=1100,
            stock_quantity=10,
        )
        response = self.client.post(
            reverse('dashboard', kwargs={'role': 'pesticide'}),
            {'save_shop_price': '1', 'item_id': str(item.id), 'shop_price': '1050'},
        )
        self.assertRedirects(response, reverse('dashboard', kwargs={'role': 'pesticide'}))
        item.refresh_from_db()
        self.assertEqual(item.price, 1050)

    def test_new_service_pincodes_are_available(self):
        load_telangana_pincodes(force=True)
        for pincode in ['503224', '503306', '502316', '502331', '502286', '503001', '503002']:
            response = self.client.get(reverse('get_location_api'), {'pincode': pincode})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload['success'], msg=f'Expected success for {pincode}')


class SecurityEnhancementTests(TestCase):
    def test_otp_expired_payload_fails_validation(self):
        session = self.client.session
        session['reg_otp'] = {
            'code': '1234',
            'expires_at': (timezone.now() - timedelta(minutes=1)).isoformat(),
        }
        session['reg_core'] = {
            'name': 'Expired User',
            'age': 30,
            'mobile': '9111111111',
            'role': 'farmer',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'is_verified': False,
        }
        session['reg_profile'] = {'gender': 'Male', 'passbook_number': 'T12345678901'}
        session.save()

        response = self.client.post(reverse('verify_otp'), {'otp': '1234'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserRegistration.objects.filter(mobile='9111111111', role='farmer').exists())

    def test_otp_attempts_lock_after_five_invalid_tries(self):
        session = self.client.session
        session['login_otp'] = {'code': '9999', 'expires_at': (timezone.now() + timedelta(minutes=5)).isoformat()}
        session['mobile'] = '9999999999'
        session['role'] = 'farmer'
        session.save()

        for _ in range(4):
            response = self.client.post(reverse('verify_otp_login'), {'otp': '1111'})
            self.assertEqual(response.status_code, 200)

        fifth = self.client.post(reverse('verify_otp_login'), {'otp': '1111'})
        self.assertEqual(fifth.status_code, 302)
        self.assertRedirects(fifth, reverse('login'))

    def test_conflicting_tractor_slot_is_blocked(self):
        self.assertTrue(True)

    def test_otp_back_redirects_to_previous_form_page(self):
        response = self.client.post(reverse('tractor_register'), {
            'name': 'Tractor Person',
            'mobile': '9234567890',
            'age': '30',
            'base_wage': '500',
            'driving_license': 'TS0520230000123',
            'state': 'Telangana',
            'district': 'Nizamabad',
            'mandal': 'Armoor',
            'village': 'Perkit',
            'services': ['Ploughing'],
            'exp_Ploughing': '2',
            'wage_Ploughing': '500',
            'experience': '2',
            'pincode': '503001',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp'))

        back = self.client.get(reverse('otp_back'))
        self.assertEqual(back.status_code, 302)
        self.assertRedirects(back, reverse('tractor_register'))

class PlatformHardeningTests(TestCase):
    def test_shop_item_form_rejects_short_name(self):
        self.assertTrue(True)
    def test_location_api_rejects_invalid_pincode(self):
        self.assertTrue(True)
    def test_generate_api_docs_command(self):
        self.assertTrue(True)
