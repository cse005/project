from django.contrib import admin

from kisan1.pincode_data import HIDDEN_PINCODES

from .models import (
    FarmerProfile,
    LaborBooking,
    LaborProfile,
    LeaseLandRequest,
    LeaseProfile,
    Order,
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


@admin.register(UserRegistration)
class UserRegistrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'mobile', 'district', 'created_at')
    list_filter = ('role',)
    search_fields = ('name', 'mobile')
    inlines = [FarmerInline, TractorInline, LaborInline, LeaseInline, ToolsInline, PesticideInline]


@admin.register(PincodeMapping)
class PincodeMappingAdmin(admin.ModelAdmin):
    list_display = ('pincode', 'village', 'mandal', 'district', 'state')
    search_fields = ('pincode', 'village', 'mandal', 'district')
    list_filter = ('district', 'mandal')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.exclude(pincode__in=[str(value) for value in HIDDEN_PINCODES])


admin.site.register(Order)
admin.site.register(ShopOrder)
admin.site.register(LaborBooking)
admin.site.register(TractorBooking)
admin.site.register(ToolRentalBooking)
admin.site.register(LeaseLandRequest)
admin.site.register(ToolInventory)
