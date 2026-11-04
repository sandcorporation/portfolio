import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0026_service_images"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="card",
            field=models.ForeignKey(
                blank=True,
                help_text="홈 카드의 2:1 썸네일(권장 1200×600). 없으면 대표 이미지를 잘라 씁니다.",
                limit_choices_to={"is_public": True, "uploaded_at__isnull": False},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="content.media",
                verbose_name="카드 썸네일",
            ),
        ),
    ]
