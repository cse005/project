from django.db import migrations


def sanitize_currency_text(apps, schema_editor):
    ToolsProfile = apps.get_model('kisan1', 'ToolsProfile')
    ToolRentalBooking = apps.get_model('kisan1', 'ToolRentalBooking')

    rupee_symbol = '\u20b9'
    mojibake_rupee = '\u00e2\u201a\u00b9'

    def clean(value):
        if not value:
            return value
        return value.replace(rupee_symbol, 'Rs. ').replace(mojibake_rupee, 'Rs. ')

    for record in ToolsProfile.objects.exclude(tools_type__isnull=True):
        updated = clean(record.tools_type)
        if updated != record.tools_type:
            record.tools_type = updated
            record.save(update_fields=['tools_type'])

    for record in ToolRentalBooking.objects.exclude(tools_selected__isnull=True):
        updated = clean(record.tools_selected)
        if updated != record.tools_selected:
            record.tools_selected = updated
            record.save(update_fields=['tools_selected'])


class Migration(migrations.Migration):
    dependencies = [
        ('kisan1', '0008_pesticideprofile_service_rate_and_more'),
    ]

    operations = [
        migrations.RunPython(sanitize_currency_text, migrations.RunPython.noop),
    ]
