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
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from threading import Thread
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

# Adjustable daily creation limit (change as needed)
DAILY_CREATION_LIMIT = getattr(settings, "DAILY_CREATION_LIMIT", 100)

# How many pages max to convert into images:
PAGE_IMAGE_LIMIT = getattr(settings, "PAGE_IMAGE_LIMIT", 15)

PENDING_ARTICLE_LIMIT = 5

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store original file paths to handle updates
        self._original_pdf_file = self.pdf_file.name if self.pdf_file else None
        self._original_cover_image = self.cover_image.name if self.cover_image else None

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
        
        # Check if PDF file has been updated
        pdf_updated = False
        if self.pdf_file and self._original_pdf_file != self.pdf_file.name:
            pdf_updated = True
            # Delete old PDF file if it exists
            if self._original_pdf_file and default_storage.exists(self._original_pdf_file):
                default_storage.delete(self._original_pdf_file)
        
        # Check if cover image has been updated
        if self.cover_image and self._original_cover_image != self.cover_image.name:
            # Delete old cover image if it exists
            if self._original_cover_image and default_storage.exists(self._original_cover_image):
                default_storage.delete(self._original_cover_image)
        
        super().save(*args, **kwargs)
        
        # Regenerate page images if PDF was updated
        if pdf_updated and self.pdf_file:
            self.generate_page_images()

        # Update the stored original file names
        self._original_pdf_file = self.pdf_file.name if self.pdf_file else None
        self._original_cover_image = self.cover_image.name if self.cover_image else None

    def delete(self, *args, **kwargs):
        if self.pdf_file:
            self.pdf_file.delete(save=False)

        if self.cover_image:
            self.cover_image.delete(save=False)

        # Delete page images
        if self.page_images:
            for page_url in self.page_images:
                # Extract file path from URL
                try:
                    # Remove domain and media URL prefix to get relative path
                    media_url = settings.MEDIA_URL
                    if page_url.startswith(media_url):
                        file_path = page_url[len(media_url):]
                        if default_storage.exists(file_path):
                            default_storage.delete(file_path)
                except Exception as e:
                    print(f"Error deleting page image {page_url}: {e}")

        # Updated folder naming convention
        folder_name = f"{self.year}_{self.season}"
        pages_folder = os.path.join(settings.MEDIA_ROOT, "magazines", "pages", folder_name)
        if os.path.isdir(pages_folder):
            shutil.rmtree(pages_folder)

        super().delete(*args, **kwargs)

    def generate_page_images(self):
        # First, delete existing page images
        if self.page_images:
            for page_url in self.page_images:
                try:
                    media_url = settings.MEDIA_URL
                    if page_url.startswith(media_url):
                        file_path = page_url[len(media_url):]
                        if default_storage.exists(file_path):
                            default_storage.delete(file_path)
                except Exception as e:
                    print(f"Error deleting old page image {page_url}: {e}")
            self.page_images = None
            self.save(update_fields=["page_images"])

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


# upload path now uses the model's custom filename
def article_upload_path(instance, filename):
    # folder by current time (you can also use instance.submitted_at if you prefer)
    now = timezone.now()
    year = now.year
    month_number = now.strftime("%m")
    month_name = calendar.month_name[now.month]

    # call the model's custom filename generator (guarantees uniqueness)
    # custom_filename should return a filename with extension
    filename = instance.custom_filename()
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
        title_snake = slugify(self.title)[:30]  # longer slice to keep more of the title
        unique_str = uuid.uuid4().hex[:8]  # short unique ID
        return f"article_{title_snake}_{self.first_name}_{unique_str}.docx"

def _send_article_email_async(article, template_name, subject):
    """
    Sends the email via ZeptoMail API asynchronously.
    """
    def send_email():
        context = {
            "author_name": f"{article.first_name} {article.last_name}",
            "article_title": article.title,
            "article": article,
        }

        html_message = render_to_string(template_name, context)
        plain_message = strip_tags(html_message)

        payload = {
            "from": {"address": settings.ZEPTO_FROM_EMAIL, "name": "Burrowed Team"},
            "to": [{"email_address": {"address": article.email, "name": f"{article.first_name} {article.last_name}"}}],
            "subject": subject,
            "htmlbody": html_message,
            "textbody": plain_message
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Zoho-enczapikey {settings.ZEPTO_API_KEY}"
        }

        try:
            response = requests.post(settings.ZEPTO_API_URL, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"Email sending failed: {e}, Response: {getattr(e, 'response', None)}")

    Thread(target=send_email).start()


@receiver(pre_save, sender=Article)
def article_pre_save(sender, instance, **kwargs):
    """
    Store previous status (if any) on instance so post_save can compare.
    """
    if instance.pk:
        try:
            old = Article.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except Article.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Article)
def article_post_save(sender, instance, created, **kwargs):
    """
    - created == True  => send acknowledgement email
    - status changed   => send accepted/rejected email
    Note: queryset.update() bypasses these signals, so admin bulk actions
    below handle that explicitly.
    """
    if created:
        try:
            _send_article_email_async(instance, "emails/acknowledge.html", "We’ve received your submission!")
        except Exception as e:
            # optionally log error: logger.exception(...)
            pass
    else:
        old_status = getattr(instance, "_old_status", None)
        new_status = instance.status
        if old_status != new_status:
            try:
                if new_status == "approved":
                    _send_article_email_async(instance, "emails/accepted.html", "Congratulations 🎉 - Your work has been shortlisted!")
                elif new_status == "rejected":
                    _send_article_email_async(instance, "emails/rejected.html", "Thank you for your submission.")
            except Exception:
                # optionally log error
                pass


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
    

class TokenUsage(models.Model):
    ip_address = models.CharField(max_length=45, primary_key=True)
    tokens_used = models.IntegerField(default=0)
    last_updated = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'token_usage'  # Optional: Explicitly set table name
        indexes = [
            models.Index(fields=['last_updated']),  # For faster queries
        ]

    def __str__(self):
        return f"{self.ip_address} - {self.tokens_used} tokens"
    
from django.db import models
from django.utils import timezone

class SeasonalSubmissionConfig(models.Model):
    SEASON_CHOICES = [
        ('Spring', 'Spring'),
        ('Summer', 'Summer'),
        ('Fall', 'Fall'),
        ('Winter', 'Winter'),
    ]

    season = models.CharField(
        max_length=20,
        choices=SEASON_CHOICES,
        help_text="Season for this issue (Spring, Summer, Fall, or Winter)."
    )
    year = models.PositiveIntegerField(
        help_text="Calendar year for the issue (e.g., 2025)."
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Set to true to make this the currently active submission configuration."
    )

    # Theme info
    theme_title = models.CharField(
        max_length=200,
        help_text="Short, human-readable title for the theme."
    )
    theme_description_1 = models.TextField(
        blank=True, null=True,
        help_text="First paragraph describing the theme (optional)."
    )
    theme_description_2 = models.TextField(
        blank=True, null=True,
        help_text="Second paragraph describing the theme (optional)."
    )
    seasonal_note = models.TextField(
        blank=True, null=True,
        help_text="Optional note or editorial comment about this season/issue."
    )

    # Dates
    submission_deadline = models.DateField(
        help_text="Final date to accept submissions (YYYY-MM-DD)."
    )
    publication_date = models.DateField(
        help_text="Planned publication date for the issue (YYYY-MM-DD)."
    )

    # Alignment text
    theme_alignment = models.TextField(
        blank=True,
        null=True,
        help_text="Short paragraph describing how submissions should align with the theme."
    )

    # Separate bullet fields for guidance
    theme_guidance_intro = models.TextField(
        blank=True,
        null=True,
        help_text="Introductory paragraph for theme guidance (optional)."
    )
    theme_bullet_1 = models.CharField(
        max_length=300, blank=True, null=True,
        help_text="Bullet point 1 (e.g., Stories of deep devotion...)."
    )
    theme_bullet_2 = models.CharField(
        max_length=300, blank=True, null=True,
        help_text="Bullet point 2."
    )
    theme_bullet_3 = models.CharField(
        max_length=300, blank=True, null=True,
        help_text="Bullet point 3."
    )
    theme_bullet_4 = models.CharField(
        max_length=300, blank=True, null=True,
        help_text="Bullet point 4."
    )
    theme_bullet_5 = models.CharField(
        max_length=300, blank=True, null=True,
        help_text="Bullet point 5."
    )

    current_issue_label_1 = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Human-readable issue label, e.g. 'Year 1 - Fall 2025'. Auto-generated."
    )
    current_issue_label_2 = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Alternative/short issue label, e.g. 'Year 1 - Fall Issue'. Auto-generated."
    )

    def __str__(self):
        return f"{self.season} {self.year} - {self.theme_title}"

    @property
    def is_submissions_open(self):
        return self.is_active and timezone.now().date() <= self.submission_deadline

    # Optional helper to return bullet list as array
    def theme_guidance_list(self):
        return [
            b for b in [
                self.theme_bullet_1,
                self.theme_bullet_2,
                self.theme_bullet_3,
                self.theme_bullet_4,
                self.theme_bullet_5,
            ] if b
        ]

    @property
    def year_number(self):
        """Calculate Year number with 2025 as Year 1."""
        return self.year - 2024

    def _generate_issue_labels(self):
        year_num = self.year_number
        label1 = f"Year {year_num} - {self.season} {self.year}"
        label2 = f"Year {year_num} - {self.season} Issue"
        return label1, label2

    def save(self, *args, **kwargs):
        """
        Behavior:
        - On create: generate labels if they were not provided.
        - On update: if season or year changed, regenerate both labels (overwrite previous).
        - Ensure only one configuration is active at a time when is_active=True.
        """
        # Determine if this is an update and if season/year changed
        regenerate_on_change = False
        if self.pk:
            try:
                old = SeasonalSubmissionConfig.objects.get(pk=self.pk)
            except SeasonalSubmissionConfig.DoesNotExist:
                old = None

            if old and (old.season != self.season or old.year != self.year):
                regenerate_on_change = True

        # Generate labels when necessary
        if regenerate_on_change:
            self.current_issue_label_1, self.current_issue_label_2 = self._generate_issue_labels()
        else:
            # Creation or labels missing: generate defaults if the user didn't supply them
            if not self.current_issue_label_1 or not self.current_issue_label_2:
                self.current_issue_label_1, self.current_issue_label_2 = self._generate_issue_labels()

        # Ensure only one active configuration at a time
        if self.is_active:
            # exclude self (if exists) to avoid turning off the instance we are saving if it's already active
            SeasonalSubmissionConfig.objects.exclude(pk=self.pk).update(is_active=False)

        super().save(*args, **kwargs)

class Banner(models.Model):
    # Route choices - using URL paths for consistency
    ROUTE_CHOICES = [
        ('/', 'Home'),
        ('/submit', 'Submit Your Work'),
        ('/contact', 'Contact'),
        ('/collaborate', 'Collaborate'),
        ('/issues', 'Issues'),
        ('/legal', 'Legal'),
        ('/about', 'About'),
        ('/faq', 'FAQ'),
        ('none', 'None'),
    ]
    
    # Main identification fields
    banner_title = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique title for this banner campaign"
    )
    
    banner_identifier = models.SlugField(
        max_length=100,
        unique=True,
        blank=True,
        help_text="Auto-generated unique identifier used for localStorage tracking"
    )
    
    # Display settings
    reset_duration_days = models.PositiveIntegerField(
        default=7,
        help_text="Number of days after which banner reappears after dismissal"
    )
    
    is_active = models.BooleanField(
        default=False,
        help_text="Only one banner can be active at a time"
    )
    
    # Banner Duration Settings
    duration_months = models.PositiveIntegerField(
        default=0,
        help_text="Duration in months (0 for no time limit)"
    )
    
    duration_days = models.PositiveIntegerField(
        default=0,
        help_text="Additional duration in days"
    )
    
    auto_deactivate_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Automatically calculated deactivation date based on duration"
    )
    
    # Desktop content
    desktop_main_text = models.CharField(
        max_length=200,
        help_text="Main text displayed on desktop version"
    )
    
    desktop_link_text = models.CharField(
        max_length=100,
        help_text="Clickable text for desktop version"
    )
    
    desktop_route = models.CharField(
        max_length=20,
        choices=ROUTE_CHOICES,
        default='none',
        help_text="Destination route for desktop click"
    )
    
    # Mobile content  
    mobile_main_text = models.CharField(
        max_length=150,
        help_text="Main text displayed on mobile version"
    )
    
    mobile_route = models.CharField(
        max_length=20,
        choices=ROUTE_CHOICES,
        default='none',
        help_text="Destination route for mobile click"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activation_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this banner was activated"
    )
    
    class Meta:
        verbose_name = "Banner"
        verbose_name_plural = "Banners"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.banner_title} ({'Active' if self.is_active else 'Inactive'})"
    
    def generate_banner_identifier(self):
        """Generate a unique banner identifier based on title and random string"""
        base_slug = slugify(self.banner_title)
        random_suffix = uuid.uuid4().hex[:8]  # 8 character random suffix
        
        # If base_slug is empty (e.g., non-english characters), use fallback
        if not base_slug:
            base_slug = "banner"
        
        identifier = f"{base_slug}-{random_suffix}"
        
        # Ensure uniqueness
        while Banner.objects.filter(banner_identifier=identifier).exists():
            random_suffix = uuid.uuid4().hex[:8]
            identifier = f"{base_slug}-{random_suffix}"
        
        return identifier
    
    def calculate_auto_deactivate_date(self):
        """Calculate the auto deactivation date based on duration settings"""
        if not self.activation_date:
            return None
            
        total_days = (self.duration_months * 30) + self.duration_days
        if total_days > 0:
            return self.activation_date + timedelta(days=total_days)
        return None
    
    def is_expired(self):
        """Check if the banner has expired based on auto_deactivate_at"""
        if self.auto_deactivate_at and timezone.now() > self.auto_deactivate_at:
            return True
        return False
    
    def clean(self):
        """Validate banner data"""
        super().clean()
        
        # Validate duration fields
        if self.duration_months == 0 and self.duration_days == 0:
            # No duration set, auto_deactivate_at should be None
            self.auto_deactivate_at = None
    
    def save(self, *args, **kwargs):
        # Generate banner identifier if not set
        if not self.banner_identifier:
            self.banner_identifier = self.generate_banner_identifier()
            
        # If this banner is being activated, deactivate all others and set duration
        if self.is_active and not self._state.adding:  # Only for updates, not new creations
            # Deactivate all other banners first
            Banner.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False, 
                activation_date=None,
                auto_deactivate_at=None
            )
            
            # Set activation date for this banner
            if not self.activation_date:
                self.activation_date = timezone.now()
                
            # Calculate auto deactivate date
            self.auto_deactivate_at = self.calculate_auto_deactivate_date()
            
        elif self.is_active and self._state.adding:
            # For new banner being created as active, deactivate all others
            Banner.objects.filter(is_active=True).update(
                is_active=False, 
                activation_date=None,
                auto_deactivate_at=None
            )
            if not self.activation_date:
                self.activation_date = timezone.now()
                
            # Calculate auto deactivate date
            self.auto_deactivate_at = self.calculate_auto_deactivate_date()
        else:
            # If deactivating, clear activation date and auto deactivate
            self.activation_date = None
            self.auto_deactivate_at = None
            
        # If duration fields are updated and banner is active, recalculate auto_deactivate_at
        if self.is_active and self.activation_date and (self.duration_months > 0 or self.duration_days > 0):
            self.auto_deactivate_at = self.calculate_auto_deactivate_date()
            
        # Run validation before saving
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_desktop_route_url(self):
        """Get the actual URL for desktop route"""
        if self.desktop_route == 'none':
            return None
        return self.desktop_route
    
    def get_mobile_route_url(self):
        """Get the actual URL for mobile route"""
        if self.mobile_route == 'none':
            return None
        return self.mobile_route
    
    def get_total_duration_days(self):
        """Get total duration in days for display"""
        return (self.duration_months * 30) + self.duration_days
    
    @classmethod
    def get_active_banner(cls):
        """Get the currently active banner, checking for expiration"""
        active_banner = cls.objects.filter(is_active=True).first()
        
        # Check if active banner has expired
        if active_banner and active_banner.is_expired():
            active_banner.is_active = False
            active_banner.activation_date = None
            active_banner.auto_deactivate_at = None
            active_banner.save()
            return None
            
        return active_banner
    
    @classmethod
    def deactivate_expired_banners(cls):
        """Deactivate all expired banners (can be called by a cron job)"""
        expired_banners = cls.objects.filter(
            is_active=True,
            auto_deactivate_at__lt=timezone.now()
        )
        count = expired_banners.count()
        expired_banners.update(
            is_active=False,
            activation_date=None,
            auto_deactivate_at=None
        )
        return count
    
    def activate(self):
        """Activate this banner and deactivate all others"""
        # Use update to avoid calling save method recursively
        Banner.objects.filter(is_active=True).update(
            is_active=False, 
            activation_date=None,
            auto_deactivate_at=None
        )
        
        # Now activate this one
        self.is_active = True
        self.activation_date = timezone.now()
        self.auto_deactivate_at = self.calculate_auto_deactivate_date()
        self.save()
    
    def deactivate(self):
        """Deactivate this banner"""
        self.is_active = False
        self.activation_date = None
        self.auto_deactivate_at = None
        self.save()
