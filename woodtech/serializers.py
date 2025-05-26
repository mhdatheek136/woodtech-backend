from rest_framework import serializers
from .models import Magazine

class MagazineSerializer(serializers.ModelSerializer):
    # Map date_uploaded → publish_date (and format it if you like)
    publish_date = serializers.DateTimeField(
        source='date_uploaded',
        format="%Y-%m-%d",        # or any datetime format string you prefer
        read_only=True
    )
    page_images = serializers.SerializerMethodField()

    class Meta:
        model = Magazine
        fields = [
            'id',
            'title',
            'publish_date',       # ← include the new field
            'volume_number',
            'season_number',
            'pdf_file',
            'cover_image',
            'description',
            'is_published',
            'page_images',
        ]
        read_only_fields = ['publish_date', 'volume_number', 'season_number']

    def get_page_images(self, obj):
        request = self.context.get('request')
        if obj.page_images:
            return [request.build_absolute_uri(url) for url in obj.page_images]
        return []


from rest_framework import serializers
from .models import Article

class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = [
            'id', 'first_name', 'last_name', 'country', 'title',
            'email', 'file', 'user_bio', 'user_note', 'submitted_at', 'status'
        ]
        read_only_fields = ['submitted_at', 'status']

    def validate(self, data):
        email = data.get('email')
        # Default to 'pending' if not explicitly passed
        status = data.get('status', 'pending')

        if status == 'pending':
            existing = Article.objects.filter(email=email, status='pending')
            if existing.exists():
                raise serializers.ValidationError({
                    'email': "You already have a pending article submitted with this email."
                })
        return data




# subscribers/serializers.py

from rest_framework import serializers
from .models import Subscriber

class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = ['name', 'email']


from rest_framework import serializers
from .models import Collaborator

class CollaboratorCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collaborator
        fields = ['name', 'email', 'brand_or_organization', 'message', 'logo_or_sample']

    def validate(self, data):
        # Enforce status='new' on creation
        data['status'] = 'new'
        
        instance = Collaborator(**data)
        # Check email count for new status
        count_new = Collaborator.objects.filter(email=data['email'], status='new').count()
        if count_new >= 3:
            raise serializers.ValidationError(
                f"You cannot have more than 3 'new' submissions with the same email ({data['email']})."
            )
        return data

    def create(self, validated_data):
        validated_data['status'] = 'new'  # enforce default status
        return super().create(validated_data)
