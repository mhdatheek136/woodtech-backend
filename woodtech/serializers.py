from rest_framework import serializers
from .models import Magazine

class MagazineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Magazine
        fields = [
            'id',
            'title',
            'date_uploaded',
            'volume_number',
            'season_number',
            'pdf_file',
            'cover_image',
            'description',
            'is_published',
        ]
        read_only_fields = ['date_uploaded', 'volume_number', 'season_number']
