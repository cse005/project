from django.contrib import admin
from .models import (
    UserRegistration, 
    FarmerProfile, 
    TractorProfile, 
    LaborProfile, 
    LeaseProfile, 
    ToolsProfile, 
    Order, 
    PesticideProfile,
    ShopOrder,
    LaborBooking,
    TractorBooking,
    ToolRentalBooking,
    LeaseLandRequest,
    PincodeMapping # ✅ Added the new model here
)

class FarmerInline(admin.StackedInline):
    model = FarmerProfile
    can_delete = False
    verbose_name_plural = 'Farmer Details'

class TractorInline(admin.StackedInline):
    model = TractorProfile
    can_delete = False
    verbose_name_plural = 'Tractor Details'

class LaborInline(admin.StackedInline):
    model = LaborProfile
    can_delete = False
    verbose_name_plural = 'Labor Details'

class LeaseInline(admin.StackedInline):
    model = LeaseProfile
    can_delete = False
    verbose_name_plural = 'Land Details'

class ToolsInline(admin.StackedInline):
    model = ToolsProfile
    can_delete = False
    verbose_name_plural = 'Tools Details'

class PesticideInline(admin.StackedInline):
    model = PesticideProfile
    can_delete = False
    verbose_name_plural = 'Shop Details'

# ✅ User Registration Block
@admin.register(UserRegistration)
class UserRegistrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'mobile', 'district', 'created_at')
    list_filter = ('role',)
    search_fields = ('name', 'mobile')
    inlines = [FarmerInline, TractorInline, LaborInline, LeaseInline, ToolsInline, PesticideInline]

# ✅ New Pincode Mapping Block
@admin.register(PincodeMapping)
class PincodeMappingAdmin(admin.ModelAdmin):
    list_display = ('pincode', 'village', 'mandal', 'district', 'state')
    search_fields = ('pincode', 'village', 'mandal', 'district')
    list_filter = ('district', 'mandal')

admin.site.register(Order)
admin.site.register(ShopOrder)
admin.site.register(LaborBooking)
admin.site.register(TractorBooking)
admin.site.register(ToolRentalBooking)
admin.site.register(LeaseLandRequest)
