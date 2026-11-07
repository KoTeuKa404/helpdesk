from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("helpdesk", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="knowledge_context",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
