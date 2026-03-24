from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from kisan1.models import (
    LaborBooking,
    PesticideInventory,
    PesticideProfile,
    ToolInventory,
    TractorBooking,
)


ALLOWED_SHOP_CATEGORIES = {'Seeds', 'Fertilizer', 'Pesticides', 'Herbicides', 'Insecticides'}
ALLOWED_SHOP_CATEGORY_ALIASES = {
    'p&f',
    'p&f&s',
    'products & fertilizers',
    'products fertilizers',
    'products & fertilizers & seeds',
}


mobile_validator = RegexValidator(
    regex=r'^[6-9][0-9]{9}$',
    message=_('Mobile number must be a valid 10-digit Indian mobile number.'),
    code='invalid_mobile',
)


class PesticideForm(forms.ModelForm):
    class Meta:
        model = PesticideProfile
        fields = ['shop_name', 'license_id', 'since_years', 'products_sold']
        widgets = {
            'shop_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Shop Name'}),
            'license_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'License ID'}),
            'since_years': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'products_sold': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Products separated by | (e.g., Urea|Seeds)'}
            ),
        }

    def clean_shop_name(self):
        value = (self.cleaned_data.get('shop_name') or '').strip()
        if len(value) < 3:
            raise forms.ValidationError(_('Shop name must be at least 3 characters long.'))
        return value

    def clean_license_id(self):
        value = (self.cleaned_data.get('license_id') or '').strip()
        if len(value) < 4:
            raise forms.ValidationError(_('License ID must be at least 4 characters long.'))
        return value


class ShopItemForm(forms.ModelForm):
    class Meta:
        model = PesticideInventory
        fields = ['item_name', 'category', 'image', 'market_price', 'price', 'stock_quantity']
        widgets = {
            'item_name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'market_price': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'stock_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def clean_category(self):
        value = (self.cleaned_data.get('category') or '').strip()
        normalized = value.lower()
        if value not in ALLOWED_SHOP_CATEGORIES and normalized not in ALLOWED_SHOP_CATEGORY_ALIASES:
            raise ValidationError(
                _('Category must be one of: Seeds, Fertilizer, Pesticides, Herbicides, Insecticides, P&F, or P&F&S.')
            )
        return value

    def clean_item_name(self):
        value = (self.cleaned_data.get('item_name') or '').strip()
        if len(value) < 2:
            raise forms.ValidationError(_('Item name must be at least 2 characters.'))
        return value

    def clean_market_price(self):
        value = self.cleaned_data.get('market_price')
        if value is None or value <= 0:
            raise ValidationError(_('Market price must be greater than 0.'))
        return value

    def clean_price(self):
        value = self.cleaned_data.get('price')
        if value is None or value <= 0:
            raise ValidationError(_('Price must be greater than 0.'))
        return value

    def clean_stock_quantity(self):
        value = self.cleaned_data.get('stock_quantity')
        if value is None or value <= 0:
            raise ValidationError(_('Stock quantity must be greater than 0.'))
        return value


class LaborBookingRequestForm(forms.ModelForm):
    class Meta:
        model = LaborBooking
        fields = ['booking_date', 'start_time', 'duration', 'location']

    def clean_duration(self):
        value = self.cleaned_data.get('duration')
        if value is None or value <= 0:
            raise ValidationError(_('Duration must be greater than 0.'))
        return value


class TractorBookingRequestForm(forms.ModelForm):
    class Meta:
        model = TractorBooking
        fields = ['booking_date', 'start_time', 'duration_hours', 'location']

    def clean_duration_hours(self):
        value = self.cleaned_data.get('duration_hours')
        if value is None or value <= 0:
            raise ValidationError(_('Duration hours must be greater than 0.'))
        return value


class ServiceSettingsForm(forms.Form):
    rate = forms.IntegerField(min_value=1)
    is_available = forms.BooleanField(required=False)
    service_status = forms.ChoiceField(choices=[('Active', 'Active'), ('Paused', 'Paused')])


class ToolInventoryForm(forms.ModelForm):
    class Meta:
        model = ToolInventory
        fields = ['tool_name', 'rate', 'rate_unit']
        widgets = {
            'tool_name': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 100}),
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'rate_unit': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_tool_name(self):
        value = (self.cleaned_data.get('tool_name') or '').strip()
        if len(value) < 2:
            raise ValidationError(_('Tool name must be at least 2 characters.'))
        return value

    def clean_rate(self):
        value = self.cleaned_data.get('rate')
        if value is None or value <= 0:
            raise ValidationError(_('Rate must be greater than 0.'))
        return value


class ToolRateUpdateForm(forms.Form):
    tool_id = forms.IntegerField(min_value=1)
    rate = forms.IntegerField(min_value=1)
