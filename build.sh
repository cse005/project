pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='admin').delete(); User.objects.create_superuser('admin','admin@gmail.com','123456')" | python manage.py shell