# Generated by Django 2.2.5 on 2020-01-29 16:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workflow_handler', '0010_auto_20200113_1314'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='status',
            field=models.CharField(default='pending', max_length=128),
        ),
    ]
