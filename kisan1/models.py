from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from kisan1.pincode_data import is_hidden_pincode


MOBILE_VALIDATOR = RegexValidator(
    regex=r'^[6-9][0-9]{9}$',
    message=_('Mobile number must be a valid 10-digit Indian mobile number.'),
)


class UserIdentity(models.Model):
    mobile = models.CharField(max_length=10, unique=True, validators=[MOBILE_VALIDATOR])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.mobile



class UserRegistration(models.Model):
    ROLE_CHOICES = (
        ('farmer', 'Farmer'),
        ('tractor', 'Tractor Driver'),
        ('labor', 'Labor'),
        ('lease', 'Leasehold Land Owner'),
        ('tools', 'Farming Tools For Rent'),
        ('pesticide', 'Fertilizer & Pesticide Shop'), 
    )
    
    name = models.CharField(max_length=100)
    # 🔥 1. REMOVED unique=True from mobile
    identity = models.ForeignKey('UserIdentity', null=True, blank=True, on_delete=models.CASCADE, related_name='roles')
    mobile = models.CharField(max_length=10, validators=[MOBILE_VALIDATOR]) 
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    age = models.PositiveIntegerField(null=True, blank=True)

    state = models.CharField(max_length=100, null=True, blank=True)
    district = models.CharField(max_length=100, null=True, blank=True)
    mandal = models.CharField(max_length=100, null=True, blank=True)
    village = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.CharField(max_length=6, null=True, blank=True)
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')

    is_available = models.BooleanField(default=True)
    service_status = models.CharField(max_length=20, default='Active')

    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # 🔥 2. ADDED THIS: Makes Mobile + Role a unique combination
    class Meta:
        unique_together = ('mobile', 'role')
        indexes = [
            models.Index(fields=['mobile', 'role']),
            models.Index(fields=['role']),
            models.Index(fields=['district']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.role})"


class FarmerProfile(models.Model):
    user = models.OneToOneField(UserRegistration, on_delete=models.CASCADE, related_name='farmer_details')
    gender = models.CharField(max_length=20, null=True, blank=True)
    passbook_number = models.CharField(max_length=100, null=True, blank=True)


class TractorProfile(models.Model):
    user = models.OneToOneField(UserRegistration, on_delete=models.CASCADE, related_name='tractor_details')
    experience = models.PositiveIntegerField(default=0)
    gender = models.CharField(max_length=20, null=True, blank=True)
    wage_amount = models.PositiveIntegerField(default=0)
    driving_license = models.CharField(max_length=20, null=True, blank=True) 
    services = models.TextField(null=True, blank=True) 

class LaborProfile(models.Model):
    user = models.OneToOneField(UserRegistration, on_delete=models.CASCADE, related_name='labor_details')
    skills = models.CharField(max_length=300, null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    wage_amount = models.PositiveIntegerField(default=0)
    wage_type = models.CharField(max_length=50, default="Per Day")


class LeaseProfile(models.Model):
    user = models.OneToOneField(UserRegistration, on_delete=models.CASCADE, related_name='lease_details')
    total_land = models.FloatField(default=0.0)
    water_facility = models.CharField(max_length=100, null=True, blank=True)
    soil_type = models.CharField(max_length=500, null=True, blank=True)
    passbook_number = models.CharField(max_length=20, null=True, blank=True)
    lease_per_day = models.PositiveIntegerField(default=0) 


class ToolsProfile(models.Model):
    user = models.OneToOneField(UserRegistration, on_delete=models.CASCADE, related_name='tools_details')
    shop_name = models.CharField(max_length=100, null=True, blank=True)
    tools_type = models.CharField(max_length=200, null=True, blank=True)
    rent_per_hour = models.PositiveIntegerField(default=0)


class ToolInventory(models.Model):
    RATE_UNIT_CHOICES = (
        ('hr', 'Per Hour'),
        ('day', 'Per Day'),
    )

    owner = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='tool_inventory')
    tool_name = models.CharField(max_length=100)
    rate = models.PositiveIntegerField(default=0)
    rate_unit = models.CharField(max_length=10, choices=RATE_UNIT_CHOICES, default='hr')
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('owner', 'tool_name')
        indexes = [
            models.Index(fields=['owner', 'tool_name']),
            models.Index(fields=['owner', 'is_available']),
        ]

    def __str__(self):
        return f"{self.tool_name} ({self.owner.name})"


class Order(models.Model):
    user = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='orders') 
    provider = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='received_orders')
    service_type = models.CharField(max_length=20)

    details = models.TextField(null=True, blank=True)
    booking_date = models.DateField(null=True, blank=True)
    hours = models.PositiveIntegerField(null=True, blank=True)

    rate = models.PositiveIntegerField(default=0)
    total_amount = models.PositiveIntegerField(default=0)
    farmer_mobile = models.CharField(max_length=10)

    is_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['provider', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user.name} -> {self.provider.name} ({self.service_type})"
class PesticideProfile(models.Model):
    user = models.OneToOneField(UserRegistration, on_delete=models.CASCADE, related_name='pesticide_details')
    shop_name = models.CharField(max_length=150)
    license_id = models.CharField(max_length=50)
    since_years = models.PositiveIntegerField(default=0)
    products_sold = models.CharField(max_length=200, null=True, blank=True)
    service_rate = models.PositiveIntegerField(default=0)
class PesticideInventory(models.Model):
    shop = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='inventory')
    item_name = models.CharField(max_length=150)
    category = models.CharField(max_length=50)
    market_price = models.PositiveIntegerField(default=1)
    price = models.PositiveIntegerField()
    stock_quantity = models.PositiveIntegerField()

    def clean(self):
        if self.market_price is None or self.market_price <= 0:
            raise ValidationError({'market_price': _('Market price must be greater than 0.')})
        if self.price is None or self.price <= 0:
            raise ValidationError({'price': _('Price must be greater than 0.')})
        if self.stock_quantity is None or self.stock_quantity <= 0:
            raise ValidationError({'stock_quantity': _('Stock quantity must be greater than 0.')})

    def __str__(self):
        return f"{self.item_name} ({self.shop.name})"


# --- BOOKING & ORDER MODELS ---

class BookingStatus(models.TextChoices):
    PENDING = 'Pending', 'Pending'
    CONFIRMED = 'Confirmed', 'Confirmed'
    REJECTED = 'Rejected', 'Rejected'
    COMPLETED = 'Completed', 'Completed'
    CANCELLED = 'Cancelled', 'Cancelled'

# 1. Labor Booking (From Sketch 1)
class LaborBooking(models.Model):
    farmer = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='labor_bookings')
    laborer = models.ForeignKey(LaborProfile, on_delete=models.CASCADE)
    booking_date = models.DateField()
    start_time = models.TimeField()
    duration = models.PositiveIntegerField(help_text="Number of hours or days")
    location = models.CharField(max_length=255)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['laborer', 'booking_date', 'start_time', 'status']),
        ]

    def __str__(self):
        return f"{self.farmer.name} booked {self.laborer.user.name} on {self.booking_date}"

# 2. Tractor Booking (From Sketch 2)
class TractorBooking(models.Model):
    farmer = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='tractor_bookings')
    tractor_owner = models.ForeignKey(TractorProfile, on_delete=models.CASCADE)
    booking_date = models.DateField()
    start_time = models.TimeField()
    duration_hours = models.PositiveIntegerField()
    location = models.CharField(max_length=255)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['tractor_owner', 'booking_date', 'start_time', 'status']),
        ]

# 3. Rented Tools Booking (From Sketch 3)
class ToolRentalBooking(models.Model):
    farmer = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='tool_bookings')
    tool_shop = models.ForeignKey(ToolsProfile, on_delete=models.CASCADE)
    tools_selected = models.TextField(help_text="E.g., Tractor: 2 hrs, Harvester: 4 hrs")
    receive_date = models.DateField()
    return_date = models.DateField()
    home_delivery = models.BooleanField(default=False)
    delivery_location = models.CharField(max_length=255, blank=True, null=True)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'created_at'])]

# 4. Lease Land Request (From Sketch 4)
class LeaseLandRequest(models.Model):
    farmer = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='lease_requests')
    land = models.ForeignKey(LeaseProfile, on_delete=models.CASCADE)
    soil_type_requested = models.CharField(max_length=100)
    duration_months = models.PositiveIntegerField()
    start_date = models.DateField()
    message_to_owner = models.TextField()
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'created_at'])]

# 5. Shop Order / Cart (From Sketch 5)
class ShopOrder(models.Model):
    farmer = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name='shop_orders')
    shop = models.ForeignKey(PesticideProfile, on_delete=models.CASCADE)
    items_ordered = models.TextField(help_text="E.g., Urea: 2 Bags, Cotton Seed: 5 Pkts")
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'created_at'])]

class PincodeMapping(models.Model):
    pincode = models.CharField(max_length=6)
    state = models.CharField(max_length=100, default="Telangana")
    district = models.CharField(max_length=100)
    mandal = models.CharField(max_length=100)
    village = models.CharField(max_length=100)

    def clean(self):
        normalized = (self.pincode or '').strip()
        if not normalized.isdigit() or not (5 <= len(normalized) <= 6):
            raise ValidationError({'pincode': _('Pincode must be a 5 or 6 digit number.')})
        if is_hidden_pincode(normalized):
            raise ValidationError({'pincode': _('This pincode is restricted and cannot be stored.')})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.pincode} - {self.village}"

    class Meta:
        indexes = [
            models.Index(fields=['pincode']),
            models.Index(fields=['district', 'mandal']),
        ]


class Location(models.Model):
    pincode = models.CharField(max_length=6, db_index=True)
    district = models.CharField(max_length=100)
    mandal = models.CharField(max_length=100)
    village = models.CharField(max_length=100)

    class Meta:
        unique_together = ('pincode', 'district', 'mandal', 'village')

    def __str__(self):
        return f"{self.pincode} - {self.village}, {self.mandal}, {self.district}"
 

class Inventory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item_name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    unit = models.CharField(max_length=20)
    market_price = models.FloatField()
    price = models.FloatField()
    stock_quantity = models.IntegerField()

    def __str__(self):
        return self.item_name
