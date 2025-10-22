from rest_framework import serializers
from .models import Magazine, Article, Subscriber, Collaborator, ContactMessage


class MagazineSerializer(serializers.ModelSerializer):
    publish_date = serializers.DateTimeField(
        source='date_uploaded',
        format="%Y-%m-%d",
        read_only=False  # Changed to allow writes
    )
    page_images = serializers.SerializerMethodField()
    season_display = serializers.CharField(source='get_season_display', read_only=True)

    class Meta:
        model = Magazine
        fields = [
            'id', 'title', 'publish_date', 'year', 'season', 'season_display',
            'pdf_file', 'cover_image', 'description', 'is_published', 'page_images'
        ]
        extra_kwargs = {
            'season': {'read_only': False}  # Ensure season is writable
        }

    def get_page_images(self, obj):
        request = self.context.get('request')
        if obj.page_images:
            return [request.build_absolute_uri(url) for url in obj.page_images]
        return []

PENDING_ARTICLE_LIMIT = 5

class ArticleSerializer(serializers.ModelSerializer):
    recaptcha_token = serializers.CharField(write_only=True)

    class Meta:
        model = Article
        fields = [
            'id', 'first_name', 'last_name', 'title',
            'email', 'file', 'user_bio', 'user_note',
            'submitted_at', 'status', 'recaptcha_token'
        ]
        read_only_fields = ['submitted_at', 'status']

    def validate(self, data):
        email = data.get('email')
        status = data.get('status', 'pending')

        if status == 'pending':
            pending_count = Article.objects.filter(email=email, status='pending').count()
            if pending_count >= PENDING_ARTICLE_LIMIT:
                raise serializers.ValidationError({
                    'email': "You can only have up to 5 pending articles with this email."
                })
        return data



class SubscriberSerializer(serializers.ModelSerializer):
    recaptcha_token = serializers.CharField(write_only=True, required=True)  # Added reCAPTCHA token

    class Meta:
        model = Subscriber
        fields = ['name', 'email', 'recaptcha_token']  # Added token to fields


class CollaboratorCreateSerializer(serializers.ModelSerializer):
    recaptcha_token = serializers.CharField(write_only=True, required=True)  # Added reCAPTCHA token

    class Meta:
        model = Collaborator
        fields = [
            'name', 'email', 'brand_or_organization', 'message', 
            'logo_or_sample', 'recaptcha_token'  # Added token to fields
        ]

    def validate(self, data):
        data['status'] = 'new'
        email = data['email']
        if Collaborator.objects.filter(email=email, status='new').count() >= 3:
            raise serializers.ValidationError(
                f"You cannot have more than 3 'new' submissions with the same email ({email})."
            )
        return data

    def create(self, validated_data):
        validated_data.pop('recaptcha_token', None)  # Remove token before saving
        validated_data['status'] = 'new'
        return super().create(validated_data)


class ContactMessageSerializer(serializers.ModelSerializer):
    recaptcha_token = serializers.CharField(write_only=True, required=True)  # Added reCAPTCHA token

    class Meta:
        model = ContactMessage
        fields = [
            'id',
            'name',
            'email',
            'message',
            'status',
            'submitted_at',
            'recaptcha_token'  # Added token to fields
        ]
        read_only_fields = ['status', 'submitted_at']

    def validate(self, data):
        # Enforce max 3 “new” messages per email
        email = data.get('email')
        # On create, instance is None
        qs_new = ContactMessage.objects.filter(email=email, status='new')
        if self.instance:
            qs_new = qs_new.exclude(pk=self.instance.pk)
        if qs_new.count() >= 3:
            raise serializers.ValidationError({
                'email': "You can only have up to 3 new contact messages for this email address."
            })
        return data

    def create(self, validated_data):
        validated_data.pop('recaptcha_token', None)  # Remove token before saving
        validated_data['status'] = 'new'
        return super().create(validated_data)
    


class AskSerializer(serializers.Serializer):
    prompt = serializers.CharField(max_length=1000, required=True, allow_blank=False)
    previous_prompt = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    previous_answer = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")

    def validate_prompt(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Prompt cannot be empty")
        return stripped

# serializers.py
from rest_framework import serializers
from .models import SeasonalSubmissionConfig

class SeasonalSubmissionConfigSerializer(serializers.ModelSerializer):
    is_submissions_open = serializers.ReadOnlyField()
    theme_guidance_list = serializers.ReadOnlyField()
    year_number = serializers.ReadOnlyField()
    
    class Meta:
        model = SeasonalSubmissionConfig
        fields = '__all__'