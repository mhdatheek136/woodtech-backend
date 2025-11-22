# articles/forms.py
from django import forms
from django.utils import timezone
from .models import SEASON_CHOICES

class ArticleBulkUpdateForm(forms.Form):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True,
        help_text="Start date of the range to update"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True,
        help_text="End date of the range to update"
    )
    season = forms.ChoiceField(
        choices=[('', '---------')] + SEASON_CHOICES,
        required=False,
        help_text="Season to set for articles in this date range"
    )
    year = forms.IntegerField(
        required=False,
        min_value=2000,
        max_value=2100,
        help_text="Year to set for articles in this date range"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError("Start date cannot be after end date.")
            if end_date > timezone.now().date():
                raise forms.ValidationError("End date cannot be in the future.")
        
        if not cleaned_data.get('season') and not cleaned_data.get('year'):
            raise forms.ValidationError("At least one of Season or Year must be provided.")
            
        return cleaned_data