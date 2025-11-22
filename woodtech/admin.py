from django.contrib import admin
from django.forms import ModelForm, ValidationError
from .models import Magazine, ContactMessage, Banner
from datetime import timedelta
from django.utils import timezone


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
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django import forms
from .models import Article, _send_article_email_async
from .forms import ArticleBulkUpdateForm

import logging
logger = logging.getLogger(__name__)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'first_name', 'last_name', 'email', 
        'status', 'submitted_at', 'download_link', 'country', 'year', 'season'
    )
    list_editable = ('status', 'season', 'year', 'country')
    list_filter = ('status', 'submitted_at', 'season', 'year', 'country')
    search_fields = ('first_name', 'last_name', 'title', 'email', 'country')
    readonly_fields = ('submitted_at', 'download_link')
    actions = ['mark_as_approved', 'mark_as_rejected', 'bulk_update_season_year']

    fieldsets = (
        (None, {
            'fields': (
                'first_name', 'last_name', 'email', 'country', 'title', 'file', 'user_bio',
                'user_note', 'submitted_at'
            )
        }),
        ('Season & Year', {
            'fields': ('season', 'year'),
            'classes': ('collapse',),
            'description': 'Set season and year manually for organizational purposes'
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
            url = reverse('admin:woodtech_article_download', args=[obj.id])
            return format_html(f'<a href="{url}" target="_blank">Download</a>')
        return "No file"
    download_link.short_description = "Download File"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:article_id>/download/', self.admin_site.admin_view(self.download_file), name='woodtech_article_download'),
            path('bulk-update-season-year/', self.admin_site.admin_view(self.bulk_update_season_year_view), name='woodtech_article_bulk_update'),
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

    def bulk_update_season_year_view(self, request):
        """
        Custom admin view for bulk updating season and year by date range
        """
        if request.method == 'POST':
            form = ArticleBulkUpdateForm(request.POST)
            if form.is_valid():
                start_date = form.cleaned_data['start_date']
                end_date = form.cleaned_data['end_date']
                season = form.cleaned_data['season']
                year = form.cleaned_data['year']
                
                # Update articles in the date range
                articles = Article.objects.filter(
                    submitted_at__date__gte=start_date,
                    submitted_at__date__lte=end_date
                )
                
                update_fields = {}
                if season:
                    update_fields['season'] = season
                if year:
                    update_fields['year'] = year
                
                updated_count = articles.update(**update_fields)
                
                messages.success(
                    request, 
                    f"Successfully updated season/year for {updated_count} articles from {start_date} to {end_date}."
                )
                return redirect('admin:woodtech_article_changelist')
        else:
            form = ArticleBulkUpdateForm()
        
        context = {
            'form': form,
            'title': 'Bulk Update Season & Year by Date Range',
            'opts': self.model._meta,
            'has_permission': True,
        }
        return render(request, 'admin/bulk_update_form.html', context)

    @admin.action(description="Update season/year for selected articles")
    def bulk_update_season_year(self, request, queryset):
        """
        Admin action to update season and year for selected articles
        """
        if 'apply' in request.POST:
            form = ArticleBulkUpdateForm(request.POST)
            if form.is_valid():
                season = form.cleaned_data['season']
                year = form.cleaned_data['year']
                
                update_fields = {}
                if season:
                    update_fields['season'] = season
                if year:
                    update_fields['year'] = year
                
                updated_count = queryset.update(**update_fields)
                
                messages.success(
                    request, 
                    f"Successfully updated season/year for {updated_count} articles."
                )
                return redirect('admin:woodtech_article_changelist')
        else:
            # Initial form with date fields hidden for selection-based update
            form = ArticleBulkUpdateForm(initial={
                'start_date': None,
                'end_date': None,
            })
            form.fields['start_date'].widget = forms.HiddenInput()
            form.fields['end_date'].widget = forms.HiddenInput()
            form.fields['start_date'].required = False
            form.fields['end_date'].required = False
        
        context = {
            'form': form,
            'title': 'Update Season & Year for Selected Articles',
            'opts': self.model._meta,
            'articles': queryset,
            'action': 'bulk_update_season_year',
        }
        return render(request, 'admin/bulk_update_form.html', context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        # Add a direct link that we can use in a template tag or just access via URL
        extra_context['bulk_update_url'] = reverse('admin:woodtech_article_bulk_update')
        return super().changelist_view(request, extra_context=extra_context)


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
from .models import TokenUsage, Conversation

@admin.register(TokenUsage)
class TokenUsageAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'tokens_used', 'last_updated']
    list_filter = ['last_updated']
    search_fields = ['ip_address']

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'agent_type', 'total_tokens', 'processing_time', 'created_at']
    list_filter = ['agent_type', 'created_at']
    search_fields = ['ip_address', 'user_input']
    readonly_fields = ['created_at']
    
    def has_add_permission(self, request):
        return False  # Conversations are auto-created only

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

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = [
        'banner_title',
        'banner_identifier',
        'is_active',
        'reset_duration_days',
        'duration_display',
        'activation_date',
        'auto_deactivate_at',
        'created_at'
    ]
    
    list_filter = ['is_active', 'created_at', 'activation_date']
    
    search_fields = ['banner_title', 'banner_identifier']
    
    readonly_fields = [
        'banner_identifier', 
        'created_at', 
        'updated_at', 
        'activation_date', 
        'auto_deactivate_at',
        'preview_banner_identifier',
        'duration_display',
        'expiry_status'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'banner_title',
                'preview_banner_identifier',
                'reset_duration_days',
                'is_active'
            )
        }),
        ('Banner Duration', {
            'fields': (
                'duration_months',
                'duration_days',
                'duration_display',
                'expiry_status',
                'auto_deactivate_at',
            )
        }),
        ('Desktop Content', {
            'fields': (
                'desktop_main_text',
                'desktop_link_text', 
                'desktop_route'
            )
        }),
        ('Mobile Content', {
            'fields': (
                'mobile_main_text',
                'mobile_route'
            )
        }),
        ('Metadata', {
            'fields': (
                'activation_date',
                'created_at',
                'updated_at'
            )
        })
    )
    
    actions = ['activate_banners', 'deactivate_banners', 'deactivate_expired_banners']
    
    def preview_banner_identifier(self, obj):
        """Display the banner identifier with help text"""
        if obj.banner_identifier:
            return format_html(
                '<code>{}</code><br><small style="color: #666;">This identifier is used for localStorage tracking</small>',
                obj.banner_identifier
            )
        return "Not generated yet"
    preview_banner_identifier.short_description = "Banner Identifier"
    
    def duration_display(self, obj):
        """Display duration in a readable format"""
        if obj.duration_months == 0 and obj.duration_days == 0:
            return "No time limit"
        
        parts = []
        if obj.duration_months > 0:
            parts.append(f"{obj.duration_months} month{'s' if obj.duration_months > 1 else ''}")
        if obj.duration_days > 0:
            parts.append(f"{obj.duration_days} day{'s' if obj.duration_days > 1 else ''}")
        
        return " + ".join(parts)
    duration_display.short_description = "Total Duration"
    
    def expiry_status(self, obj):
        """Display expiry status"""
        if not obj.is_active:
            return "Not active"
        
        if not obj.auto_deactivate_at:
            return "No expiry"
        
        now = timezone.now()
        if obj.auto_deactivate_at > now:
            time_left = obj.auto_deactivate_at - now
            days = time_left.days
            hours = time_left.seconds // 3600
            
            if days > 0:
                return format_html('<span style="color: green;">Expires in {} days</span>', days)
            else:
                return format_html('<span style="color: orange;">Expires in {} hours</span>', hours)
        else:
            return format_html('<span style="color: red;">EXPIRED</span>')
    expiry_status.short_description = "Expiry Status"
    
    def activate_banners(self, request, queryset):
        """Admin action to activate selected banners (only first one will work)"""
        if queryset.count() > 1:
            self.message_user(request, "Only one banner can be active at a time. Activating the first selected banner.", level='warning')
        
        # Deactivate ALL banners first
        Banner.objects.filter(is_active=True).update(
            is_active=False, 
            activation_date=None,
            auto_deactivate_at=None
        )
        
        # Activate the first selected banner
        banner_to_activate = queryset.first()
        banner_to_activate.is_active = True
        banner_to_activate.activation_date = timezone.now()
        banner_to_activate.auto_deactivate_at = banner_to_activate.calculate_auto_deactivate_date()
        banner_to_activate.save()
        
        self.message_user(request, f"Banner '{banner_to_activate.banner_title}' activated successfully. All other banners were deactivated.")
    
    activate_banners.short_description = "Activate selected banner"
    
    def deactivate_banners(self, request, queryset):
        """Admin action to deactivate selected banners"""
        updated_count = queryset.update(
            is_active=False, 
            activation_date=None,
            auto_deactivate_at=None
        )
        self.message_user(request, f"{updated_count} banner(s) deactivated successfully")
    
    deactivate_banners.short_description = "Deactivate selected banners"
    
    def deactivate_expired_banners(self, request, queryset):
        """Admin action to deactivate expired banners"""
        count = Banner.deactivate_expired_banners()
        self.message_user(request, f"{count} expired banner(s) deactivated successfully")
    
    deactivate_expired_banners.short_description = "Deactivate expired banners"

    def save_model(self, request, obj, form, change):
        """
        Override save_model to ensure only one active banner
        when saving from admin interface
        """
        if obj.is_active:
            # Deactivate all other banners
            Banner.objects.filter(is_active=True).exclude(pk=obj.pk).update(
                is_active=False, 
                activation_date=None,
                auto_deactivate_at=None
            )
            
            # Set activation date and calculate auto deactivate if not set
            if not obj.activation_date:
                obj.activation_date = timezone.now()
                
            # Calculate auto deactivate date if duration is set
            if obj.duration_months > 0 or obj.duration_days > 0:
                obj.auto_deactivate_at = obj.calculate_auto_deactivate_date()
        
        super().save_model(request, obj, form, change)
