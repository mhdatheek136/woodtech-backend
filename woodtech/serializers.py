from rest_framework import serializers
from .models import Magazine

class MagazineSerializer(serializers.ModelSerializer):
    page_images = serializers.SerializerMethodField()

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
            'page_images',
        ]
        read_only_fields = ['date_uploaded', 'volume_number', 'season_number']

    def get_page_images(self, obj):
        request = self.context.get('request')
        if obj.page_images:
            # Build full URLs for each page image
            return [request.build_absolute_uri(url) for url in obj.page_images]
        return []
