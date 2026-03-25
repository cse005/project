from django.http import HttpResponse
from django.contrib.auth.models import User

def create_admin_view(request):
    User.objects.filter(username="admin").delete()
    User.objects.create_superuser("admin", "admin@gmail.com", "123456")
    return HttpResponse("Admin created successfully")