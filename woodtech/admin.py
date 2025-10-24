from django.contrib import admin
from django.forms import ModelForm, ValidationError
from .models import Magazine, ContactMessage


admin.site.site_header = "Burrowed Admin"
admin.site.site_title = "Burrowed Admin Portal"
admin.site.index_title = "Welcome to Burrowed Admin"


class MagazineAdminForm(ModelForm):
    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get("year")
        season = cleaned_data.get("season")

        if year and season:
            qs = Magazine.objects.filter(year=year, season=season)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("This Year and Season combination already exists.")

        return cleaned_data


@admin.register(Magazine)
class MagazineAdmin(admin.ModelAdmin):
    form = MagazineAdminForm

    # Fields to display in the edit form
    fields = (
        'title', 'description', 'year', 'season', 
        'date_uploaded', 'pdf_file', 'cover_image', 'is_published'
    )
    list_display = ('title', 'year', 'season', 'date_uploaded', 'is_published')
    list_editable = ('date_uploaded', 'is_published')  # Make date editable in list view
    list_filter = ('is_published', 'year', 'season')
    search_fields = ('title',)
    date_hierarchy = 'date_uploaded'  # Add date-based navigation


# articles/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.http import FileResponse
from .models import Article
from django.urls import reverse
from django.contrib import messages
from .models import Article, _send_article_email_async

import logging
logger = logging.getLogger(__name__)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'first_name', 'last_name', 'email',
        'submitted_at', 'status', 'download_link'
    )
    list_editable = ('status',)  # 👈 Make status editable in list view
    list_filter = ('status', 'submitted_at')
    search_fields = ('first_name', 'last_name', 'title', 'email')
    readonly_fields = ('submitted_at', 'download_link')
    actions = ['mark_as_approved', 'mark_as_rejected']

    fieldsets = (
        (None, {
            'fields': (
                'first_name', 'last_name', 'email', 'title', 'file', 'user_bio',
                'user_note', 'submitted_at'
            )
        }),
        ('Review & Admin', {
            'fields': ('status', 'admin_note', 'download_link')
        }),
    )

    def save_model(self, request, obj, form, change):
        try:
            obj.full_clean()
            obj.save()
        except ValidationError as e:
            self.message_user(request, f"Error: {e.messages[0]}", level=messages.ERROR)

    def download_link(self, obj):
        if obj.file:
            url = reverse('admin:article-download', args=[obj.id])
            return format_html(f'<a href="{url}" target="_blank">Download</a>')
        return "No file"
    download_link.short_description = "Download File"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:article_id>/download/', self.admin_site.admin_view(self.download_file), name='article-download'),
        ]
        return custom_urls + urls

    def download_file(self, request, article_id):
        from django.core.files.storage import default_storage
        from django.http import Http404, HttpResponseServerError
        
        article = Article.objects.get(pk=article_id)
        if not article.file:
            raise Http404("File not found")
        
        try:
            # Use storage API for S3 access
            file = default_storage.open(article.file.name, 'rb')
            
            # Generate proper filename
            filename = article.custom_filename()
            
            # Create streaming response
            response = FileResponse(file, as_attachment=True, filename=filename)
            
            # Set content type based on file extension
            if filename.endswith('.pdf'):
                response['Content-Type'] = 'application/pdf'
            elif filename.endswith('.docx'):
                response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif filename.endswith('.doc'):
                response['Content-Type'] = 'application/msword'
                
            return response
        
        except Exception as e:
            # Log the error for debugging
            logger.error(f"Error downloading file: {str(e)}")
            return HttpResponseServerError(f"Error downloading file: {str(e)}")
        
    @admin.action(description="Mark selected articles as Approved")
    def mark_as_approved(self, request, queryset):
        articles = list(queryset)  # evaluate queryset now
        updated = queryset.update(status='approved')
        # Send emails manually for each article (refresh to be safe)
        for art in articles:
            art.refresh_from_db()
            try:
               _send_article_email_async(art, "emails/accepted.html", "Congratulations 🎉 - Your work has been shortlisted!")
            except Exception:
                pass
        self.message_user(request, f"{updated} article(s) marked as approved.")

    @admin.action(description="Mark selected articles as Rejected")
    def mark_as_rejected(self, request, queryset):
        articles = list(queryset)
        updated = queryset.update(status='rejected')
        for art in articles:
            art.refresh_from_db()
            try:
                _send_article_email_async(art, "emails/rejected.html", "Thank you for your submission.")
            except Exception:
                pass
        self.message_user(request, f"{updated} article(s) marked as rejected.")


# subscribers/admin.py

from django.contrib import admin
from import_export.admin import ExportMixin
from .models import Subscriber

@admin.register(Subscriber)
class SubscriberAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ('name', 'email', 'subscribed_at')
    search_fields = ('email', 'name')

from django.contrib import admin
from .models import Collaborator

@admin.register(Collaborator)
class CollaboratorAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        'name', 'email', 'brand_or_organization', 'status', 
        'submitted_at', 'last_updated'
    )
    list_editable = ('status',)  # 👈 This line makes it editable inline in list
    list_filter = ('status', 'submitted_at')
    search_fields = ('email', 'name', 'brand_or_organization', 'message')
    readonly_fields = ('submitted_at', 'last_updated')

@admin.register(ContactMessage)
class ContactMessageAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        'name',
        'email',
        'status',
        'submitted_at',
    )
    list_editable = (
        'status',
    )
    list_filter = (
        'status',
        'submitted_at',
    )
    search_fields = (
        'name',
        'email',
        'message',
    )
    readonly_fields = (
        'submitted_at',
    )


# admin.py
from django.contrib import admin
from .models import TokenUsage

@admin.register(TokenUsage)
class TokenUsageAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'tokens_used', 'last_updated')
    search_fields = ('ip_address',)
    readonly_fields = ('last_updated',)
    list_filter = ('last_updated',)

from django.contrib import admin
from .models import SeasonalSubmissionConfig

@admin.register(SeasonalSubmissionConfig)
class SeasonalSubmissionConfigAdmin(admin.ModelAdmin):
    list_display = [
        'season',
        'year',
        'theme_title',
        'current_issue_label_1',
        'current_issue_label_2',
        'submission_deadline',
        'publication_date',
        'is_active',
        'is_submissions_open',
    ]
    
    list_filter = ['season', 'year', 'is_active']
    search_fields = [
        'theme_title',
        'theme_description_1',
        'theme_description_2',
        'seasonal_note',
        'theme_alignment',
        'theme_bullet_1',
        'theme_bullet_2',
        'theme_bullet_3',
        'theme_bullet_4',
        'theme_bullet_5',
    ]
    
    # Make the auto-generated labels and computed field read-only
    readonly_fields = ['current_issue_label_1', 'current_issue_label_2', 'is_submissions_open']
    
    fieldsets = (
        ('Season Info', {
            'fields': ('season', 'year', 'is_active', 'current_issue_label_1', 'current_issue_label_2')
        }),
        ('Theme Content', {
            'fields': ('theme_title', 'theme_description_1', 'theme_description_2', 'seasonal_note')
        }),
        ('Theme Alignment & Guidance', {
            'fields': (
                'theme_alignment',
                'theme_guidance_intro',
                'theme_bullet_1',
                'theme_bullet_2',
                'theme_bullet_3',
                'theme_bullet_4',
                'theme_bullet_5',
            )
        }),
        ('Dates', {
            'fields': ('submission_deadline', 'publication_date')
        }),
    )
