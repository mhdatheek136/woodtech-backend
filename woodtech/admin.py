from django.contrib import admin
from django.forms import ModelForm, ValidationError
from .models import Magazine


class MagazineAdminForm(ModelForm):
    def clean(self):
        cleaned_data = super().clean()
        volume = cleaned_data.get("volume_number")
        season = cleaned_data.get("season_number")

        if volume and season:
            qs = Magazine.objects.filter(volume_number=volume, season_number=season)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("This Volume and Season combination already exists.")

        return cleaned_data


@admin.register(Magazine)
class MagazineAdmin(admin.ModelAdmin):
    form = MagazineAdminForm

    fields = (
        'title',
        'description',
        'volume_number',
        'season_number',
        'is_published',
        'date_uploaded',
    )

    list_display = ('title', 'volume_number', 'season_number', 'date_uploaded', 'is_published')
    list_filter = ('is_published', 'volume_number')
    search_fields = ('title',)

    readonly_fields = ('date_uploaded',)


# articles/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.http import FileResponse
from .models import Article
from django.urls import reverse
from django.contrib import messages



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
        article = Article.objects.get(pk=article_id)
        file_path = article.file.path
        filename = article.custom_filename()
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)

    @admin.action(description="Mark selected articles as Approved")
    def mark_as_approved(self, request, queryset):
        updated = queryset.update(status='approved')
        self.message_user(request, f"{updated} article(s) marked as approved.")

    @admin.action(description="Mark selected articles as Rejected")
    def mark_as_rejected(self, request, queryset):
        updated = queryset.update(status='rejected')
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
class CollaboratorAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'email', 'brand_or_organization', 'status', 
        'submitted_at', 'last_updated'
    )
    list_filter = ('status', 'submitted_at')
    search_fields = ('email', 'name', 'brand_or_organization', 'message')
    readonly_fields = ('submitted_at', 'last_updated')