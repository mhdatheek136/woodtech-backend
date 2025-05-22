from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from pdf2image import convert_from_path
from PIL import Image
import os
import shutil

# Upload paths
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

# File validators
def validate_pdf(file):
    header = file.read(512)
    file.seek(0)
    if not header.startswith(b'%PDF-'):
        raise ValidationError("Uploaded file is not a valid PDF.")

def validate_image(file):
    try:
        img = Image.open(file)
        img.verify()
        fmt = img.format.lower()
        if fmt not in ('jpeg', 'png', 'gif', 'bmp'):
            raise ValidationError("Unsupported image format.")
    except Exception:
        raise ValidationError("Invalid image file.")

# Magazine model
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

    # New: list of image URLs for flipbook
    page_images = models.JSONField(blank=True, null=True)

    class Meta:
        unique_together = ('volume_number', 'season_number')

    def clean(self):
        # Ensure volume + season combo is unique
        if Magazine.objects.filter(
            volume_number=self.volume_number,
            season_number=self.season_number
        ).exclude(pk=self.pk).exists():
            raise ValidationError({
                "season_number": "This Volume and Season combination already exists."
            })

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Save first (need pdf_file.path)

        # Convert PDF to images and store paths
        if self.pdf_file and not self.page_images:
            self.generate_page_images()

    def delete(self, *args, **kwargs):
        # Delete the PDF file
        if self.pdf_file and os.path.isfile(self.pdf_file.path):
            os.remove(self.pdf_file.path)
        
        # Delete the cover image file
        if self.cover_image and os.path.isfile(self.cover_image.path):
            os.remove(self.cover_image.path)

        # Delete the generated page images folder
        folder_name = f"vol{self.volume_number}_issue{self.season_number}"
        pages_folder = os.path.join(settings.MEDIA_ROOT, 'magazines', 'pages', folder_name)
        if os.path.isdir(pages_folder):
            shutil.rmtree(pages_folder)

        # Finally delete the model instance
        super().delete(*args, **kwargs)

    def generate_page_images(self):
        # Absolute path to the uploaded PDF
        pdf_path = self.pdf_file.path

        # Destination directory
        folder_name = f"vol{self.volume_number}_issue{self.season_number}"
        output_dir = os.path.join(settings.MEDIA_ROOT, 'magazines', 'pages', folder_name)
        os.makedirs(output_dir, exist_ok=True)

        # Convert PDF to images
        images = convert_from_path(pdf_path, dpi=200)

        page_urls = []
        for i, page in enumerate(images, start=1):
            filename = f"page_{i}.png"
            abs_path = os.path.join(output_dir, filename)
            page.save(abs_path, 'PNG')

            # URL to be used by frontend
            url = f"/media/magazines/pages/{folder_name}/{filename}"
            page_urls.append(url)

        self.page_images = page_urls
        self.save(update_fields=["page_images"])

    def __str__(self):
        return f"{self.title} - Vol {self.volume_number}, Issue {self.season_number}"
