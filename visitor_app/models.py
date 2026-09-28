from django.db import models

class User(models.Model):
    user_id = models.AutoField(primary_key=True)
    user_name = models.CharField(max_length=100)
    user_gender = models.CharField(max_length=10)
    user_age = models.IntegerField()
    user_email = models.EmailField(max_length=100,unique=True)
    user_password = models.CharField(max_length=128)
    user_active = models.BooleanField(default=True)

