from django.db import models, transaction
from django.utils import timezone
import os
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from PIL import Image


def magazine_pdf_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    title_slug = slugify(instance.title)
    new_filename = f"{title_slug}_vol{instance.volume_number}_issue{instance.season_number}.{ext}"
    return os.path.join('magazines', new_filename)

def magazine_cover_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    title_slug = slugify(instance.title)
    new_filename = f"{title_slug}_vol{instance.volume_number}_issue{instance.season_number}_cover.{ext}"
    return os.path.join('magazines', 'covers', new_filename)

# Validators—only checking file headers/types
def validate_pdf(file):
    header = file.read(512)
    file.seek(0)
    if not header.startswith(b'%PDF-'):
        raise ValidationError("Uploaded file is not a valid PDF.")

def validate_image(file):
    try:
        img = Image.open(file)
        img.verify()  # will raise if not an image
        fmt = img.format.lower()
        if fmt not in ('jpeg', 'png', 'gif', 'bmp'):
            raise ValidationError("Unsupported image format.")
    except Exception:
        raise ValidationError("Invalid image file.")
    
class Magazine(models.Model):
    title = models.CharField(max_length=200)
    date_uploaded = models.DateTimeField(auto_now_add=True)
    volume_number = models.PositiveIntegerField()
    season_number = models.PositiveIntegerField()
    
    pdf_file = models.FileField(
        upload_to=magazine_pdf_upload_path,
        validators=[validate_pdf]
    )
    cover_image = models.ImageField(
        upload_to=magazine_cover_upload_path,
        blank=True, null=True,
        validators=[validate_image]
    )
    description = models.TextField(blank=True, null=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        unique_together = ('volume_number', 'season_number')

    def clean(self):
        if Magazine.objects.filter(
            volume_number=self.volume_number,
            season_number=self.season_number
        ).exclude(pk=self.pk).exists():
            raise ValidationError(
                {"season_number": "This Volume and Season combination already exists."}
            )

    def __str__(self):
        return f"{self.title} - Vol {self.volume_number}, Issue {self.season_number}"
