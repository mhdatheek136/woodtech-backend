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

    list_display = ('title', 'volume_number', 'season_number', 'date_uploaded', 'is_published')
    list_filter = ('is_published', 'volume_number')
    search_fields = ('title',)

    readonly_fields = ('date_uploaded',)
