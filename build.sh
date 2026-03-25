pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

echo "from django.contrib.auth.models import User; User.objects.filter(username='admin').delete(); User.objects.create_superuser('admin','admin@gmail.com','123456')" | python manage.py shell