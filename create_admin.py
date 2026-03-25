from django.contrib.auth import get_user_model

User = get_user_model()

# DELETE old user if exists (important)
User.objects.filter(username="admin").delete()

# CREATE fresh superuser
User.objects.create_superuser(
    username="admin",
    email="admin@gmail.com",
    password="123456"
)

print("Fresh superuser created")