from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from pdf2image import convert_from_path
import uuid
from PIL import Image
import os
import shutil
import calendar
from datetime import datetime
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from pdf2image import convert_from_path
from PIL import Image
import os
import shutil
import tempfile
import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from io import BytesIO
from pdf2image import convert_from_path
import tempfile
import requests
import os

# Adjustable daily creation limit (change as needed)
DAILY_CREATION_LIMIT = getattr(settings, "DAILY_CREATION_LIMIT", 100)

# How many pages max to convert into images:
PAGE_IMAGE_LIMIT = getattr(settings, "PAGE_IMAGE_LIMIT", 15)

# Upload paths
def magazine_pdf_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    title_slug = slugify(instance.title)
    new_filename = f"{title_slug}_{instance.year}_{instance.season}.{ext}"
    return os.path.join("magazines", new_filename)


def magazine_cover_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    title_slug = slugify(instance.title)
    new_filename = f"{title_slug}_{instance.year}_{instance.season}_cover.{ext}"
    return os.path.join("magazines", "covers", new_filename)


# File validators remain the same
def validate_pdf(file):
    header = file.read(512)
    file.seek(0)
    if not header.startswith(b"%PDF-"):
        raise ValidationError("Uploaded file is not a valid PDF.")


def validate_image(file):
    try:
        img = Image.open(file)
        img.verify()
        fmt = img.format.lower()
        if fmt not in ("jpeg", "png", "gif", "bmp"):
            raise ValidationError("Unsupported image format.")
    except Exception:
        raise ValidationError("Invalid image file.")


class Magazine(models.Model):
    # Season choices
    SEASON_CHOICES = [
        ('Winter', 'Winter'),
        ('Spring', 'Spring'),
        ('Summer', 'Summer'),
        ('Fall', 'Fall'),
    ]

    title = models.CharField(max_length=200)
    date_uploaded = models.DateTimeField(
        default=timezone.now,  # Set current time as default
        verbose_name="Upload Date",
        help_text="Date when this item was uploaded"
    )

    # Changed from volume/season to year/season
    year = models.PositiveIntegerField()
    season = models.CharField(max_length=6, choices=SEASON_CHOICES, default='Summer')

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
    page_images = models.JSONField(blank=True, null=True)

    class Meta:
        unique_together = ("year", "season")  # Updated unique constraint

    def clean(self):
        # 1) Ensure year + season combo is unique
        if Magazine.objects.filter(
            year=self.year,
            season=self.season
        ).exclude(pk=self.pk).exists():
            raise ValidationError({
                "season": "This Year and Season combination already exists."
            })

        # 2) Rate limiting remains the same
        today = timezone.now().date()
        existing_count = Magazine.objects.filter(date_uploaded__date=today).exclude(pk=self.pk).count()
        if existing_count >= DAILY_CREATION_LIMIT:
            raise ValidationError(
                f"Daily magazine creation limit reached ({DAILY_CREATION_LIMIT} per day)."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        if self.pdf_file and not self.page_images:
            self.generate_page_images()

    def delete(self, *args, **kwargs):
        if self.pdf_file:
            self.pdf_file.delete(save=False)

        if self.cover_image:
            self.cover_image.delete(save=False)

        # Updated folder naming convention
        folder_name = f"{self.year}_{self.season}"
        pages_folder = os.path.join(settings.MEDIA_ROOT, "magazines", "pages", folder_name)
        if os.path.isdir(pages_folder):
            shutil.rmtree(pages_folder)

        super().delete(*args, **kwargs)

    def generate_page_images(self):
        # Download PDF to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            response = requests.get(self.pdf_file.url, timeout=30)
            tmp.write(response.content)
            tmp_path = tmp.name

        # Convert only a few pages with lower DPI
        try:
            images = convert_from_path(
                tmp_path,
                dpi=150,  # lower DPI to reduce RAM/CPU
                first_page=1,
                last_page=PAGE_IMAGE_LIMIT
            )
        except Exception as e:
            print("PDF conversion failed:", e)
            return

        # Folder structure
        folder_name = f"magazines/pages/{self.year}_{self.season}"
        page_urls = []

        for i, page in enumerate(images, start=1):
            filename = f"{folder_name}/page_{i}.jpg"
            buffer = BytesIO()

            try:
                page.save(buffer, format="JPEG", optimize=True, quality=75)
            except Exception:
                # fallback to PNG if JPEG fails
                buffer = BytesIO()
                filename = filename.replace(".jpg", ".png")
                page.save(buffer, format="PNG")

            buffer.seek(0)
            default_storage.save(filename, ContentFile(buffer.read()))
            page_urls.append(default_storage.url(filename))

        self.page_images = page_urls
        self.save(update_fields=["page_images"])

    def __str__(self):
        return f"{self.title} - {self.year} {self.season}"  # Updated string representation


def article_upload_path(instance, filename):
    now = datetime.now()
    year = now.year
    month_number = now.strftime("%m")
    month_name = calendar.month_name[now.month]
    return f"articles/{year}/{month_number}/{month_name}/{filename}"


def validate_docx(value):
    if not value.name.endswith(".docx"):
        raise ValidationError("Only .docx files are allowed.")
    
    # Read up to 10MB in memory
    max_size = 10 * 1024 * 1024
    value.seek(0, os.SEEK_END)
    file_size = value.tell()
    value.seek(0)

    if file_size > max_size:
        raise ValidationError("File size must be under 10MB.")



STATUS_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]

PENDING_ARTICLE_LIMIT = 1


class Article(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    email = models.EmailField()
    file = models.FileField(upload_to=article_upload_path, validators=[validate_docx])

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    user_note = models.TextField(blank=True, null=True)
    user_bio = models.TextField(blank=True, null=True)
    admin_note = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # 1) Prevent more than PENDING_ARTICLE_LIMIT 'pending' articles per email
        if self.status == "pending":
            qs = Article.objects.filter(email=self.email, status="pending")
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.count() >= PENDING_ARTICLE_LIMIT:
                raise ValidationError(
                    f"You can only have {PENDING_ARTICLE_LIMIT} pending article(s) at a time for this email."
                )

        # 2) Rate limiting: max DAILY_CREATION_LIMIT articles per day
        today = timezone.now().date()
        existing_count = Article.objects.filter(submitted_at__date=today).exclude(pk=self.pk).count()
        if existing_count >= DAILY_CREATION_LIMIT:
            raise ValidationError(
                f"Daily article creation limit reached ({DAILY_CREATION_LIMIT} per day)."
            )

    def save(self, *args, **kwargs):
        # Run clean() before saving to enforce both pending-limit and daily-limit
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} by {self.first_name} {self.last_name}"

    def custom_filename(self):
        title_snake = slugify(self.title)[:15]
        month_str = self.submitted_at.strftime("%Y%m") if self.submitted_at else "unknown"
        return f"article_{self.id}_{title_snake}_{month_str}_{self.first_name}.docx"


class Subscriber(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField()
    subscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-subscribed_at"]

    def clean(self):
        """
        Only count as a "new subscription" if:
          • self.pk is None (so it really is about to INSERT), AND
          • there is no existing Subscriber with the same email on this date.
        Otherwise (updating the same email today), skip the rate-limit check.
        """
        today = timezone.now().date()

        # If updating an existing record, skip the rate-limit entirely
        if self.pk is not None:
            return

        # If an entry with this same email already exists today, treat it as an update—skip limit
        already_today = Subscriber.objects.filter(
            email=self.email,
            subscribed_at__date=today
        ).exists()
        if already_today:
            return

        # Otherwise, count how many new subscribers there have been today
        total_today = Subscriber.objects.filter(subscribed_at__date=today).count()
        if total_today >= DAILY_CREATION_LIMIT:
            raise ValidationError(
                f"Daily subscription limit reached ({DAILY_CREATION_LIMIT} per day)."
            )

    def save(self, *args, **kwargs):
        # Validate first (rate limit, etc.)
        self.full_clean()

        # Only delete older entries if this is a new record (pk is None)
        if self.pk is None:
            Subscriber.objects.filter(email=self.email).delete()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


COLLAB_STATUS = [
    ("new", "New"),
    ("in_review", "In Review"),
    ("approved", "Approved"),
    ("declined", "Declined"),
]

def collaborator_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    return f"collaborators/{instance.email}/{unique_name}"


class Collaborator(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    brand_or_organization = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    logo_or_sample = models.FileField(upload_to=collaborator_upload_path, blank=True, null=True)

    status = models.CharField(max_length=20, choices=COLLAB_STATUS, default="new")
    internal_notes = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def clean(self):
        # 1) Prevent more than 3 'new' submissions per email
        if self.status == "new":
            count_new = Collaborator.objects.filter(email=self.email, status="new")
            if self.pk:
                count_new = count_new.exclude(pk=self.pk)
            if count_new.count() >= 3:
                raise ValidationError(
                    f"You cannot have more than 3 'new' submissions with the same email ({self.email})."
                )

        # 2) Rate limiting: max DAILY_CREATION_LIMIT collaborators per day
        today = timezone.now().date()
        existing_count = Collaborator.objects.filter(submitted_at__date=today).exclude(pk=self.pk).count()
        if existing_count >= DAILY_CREATION_LIMIT:
            raise ValidationError(
                f"Daily collaborator creation limit reached ({DAILY_CREATION_LIMIT} per day)."
            )

    def save(self, *args, **kwargs):
        # Ensure clean() is called (validations + rate-limit) before save
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.email}"


CONTACT_STATUS = [
    ("new", "New"),
    ("read", "Read"),
    ("replied", "Replied"),
]

class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=CONTACT_STATUS,
        default="new",
        help_text="The current state of this message."
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Contact Us Message"
        verbose_name_plural = "Contact Us Messages"

    def clean(self):
        # 1) Prevent more than 3 “new” messages per email
        if self.status == "new":
            qs_new = ContactMessage.objects.filter(email=self.email, status="new")
            if self.pk:
                qs_new = qs_new.exclude(pk=self.pk)
            if qs_new.count() >= 3:
                raise ValidationError({
                    "status": "You can only have up to 3 new contact messages for this email address."
                })

        # 2) Rate limiting: max DAILY_CREATION_LIMIT messages per day
        today = timezone.now().date()
        qs_today = ContactMessage.objects.filter(submitted_at__date=today)
        if self.pk:
            qs_today = qs_today.exclude(pk=self.pk)
        if qs_today.count() >= DAILY_CREATION_LIMIT:
            raise ValidationError({
                "__all__": f"Daily contact message creation limit reached ({DAILY_CREATION_LIMIT} per day)."
            })

    def save(self, *args, **kwargs):
        # Enforce validations
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Contact from {self.name} <{self.email}> ({self.get_status_display()})"