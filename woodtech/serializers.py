from rest_framework import serializers
from .models import Magazine, Article, Subscriber, Collaborator, ContactMessage


class MagazineSerializer(serializers.ModelSerializer):
    publish_date = serializers.DateTimeField(
        source='date_uploaded',
        format="%Y-%m-%d",
        read_only=True
    )
    page_images = serializers.SerializerMethodField()

    class Meta:
        model = Magazine
        fields = [
            'id', 'title', 'publish_date', 'volume_number', 'season_number',
            'pdf_file', 'cover_image', 'description', 'is_published', 'page_images'
        ]
        read_only_fields = ['publish_date']  # removed volume_number & season_number here

    def get_page_images(self, obj):
        request = self.context.get('request')
        if obj.page_images:
            return [request.build_absolute_uri(url) for url in obj.page_images]
        return []


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = [
            'id', 'first_name', 'last_name', 'title',
            'email', 'file', 'user_bio', 'user_note', 'submitted_at', 'status'
        ]
        read_only_fields = ['submitted_at', 'status']

    def validate(self, data):
        email = data.get('email')
        status = data.get('status', 'pending')

        if status == 'pending':
            if Article.objects.filter(email=email, status='pending').exists():
                raise serializers.ValidationError({
                    'email': "You already have a pending article submitted with this email."
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