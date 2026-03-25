from django.contrib.auth import get_user_model

User = get_user_model()

user, created = User.objects.get_or_create(username="admin")

user.set_password("123456")
user.is_staff = True
user.is_superuser = True
user.save()

print("Admin ready")