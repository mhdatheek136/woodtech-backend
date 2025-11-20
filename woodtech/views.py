import logging
import requests
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.exceptions import ValidationError as DjangoValidationError
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited  
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from .models import Magazine, Article, Subscriber, Collaborator, ContactMessage
from .serializers import (
    MagazineSerializer,
    ArticleSerializer,
    SubscriberSerializer,
    CollaboratorCreateSerializer,
    ContactMessageSerializer,
    AskSerializer
)

logger = logging.getLogger(__name__)

@csrf_exempt
def ping_view(request):
    return JsonResponse({"message": "pong"})

def verify_recaptcha(token):
    payload = {
        'secret': settings.RECAPTCHA_SECRET_KEY,
        'response': token
    }
    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data=payload,
            timeout=5
        )
        result = response.json()

        if result.get('success', False):
            print("✅ reCAPTCHA verification successful:", result)
            return True
        else:
            print("❌ reCAPTCHA verification failed:", result)
            return False

    except requests.RequestException as e:
        print("⚠️ reCAPTCHA request failed:", e)
        return False

# Custom mixin to handle rate limiting
class RateLimitHandlerMixin:
    def handle_exception(self, exc):
        if isinstance(exc, Ratelimited):
            return Response(
                {"detail": "Too many requests. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        return super().handle_exception(exc)

# Decorator for function-based views
def handle_ratelimit(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Ratelimited:
            return JsonResponse(
                {"detail": "Too many requests. Please try again later."},
                status=429
            )
    return wrapper

@ensure_csrf_cookie
def get_csrf_token(request):
    return JsonResponse({"message": "CSRF cookie set"})

# Health check with rate limit handling
@handle_ratelimit
@ratelimit(key='ip', rate='100/m', block=True)
def health_check(request):
    return JsonResponse({"status": "ok"})

class MagazinePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

@method_decorator(ratelimit(key='ip', rate='100/m', block=True), name='dispatch')
class MagazineListListAPIView(RateLimitHandlerMixin, APIView):
    def get(self, request):
        magazines = Magazine.objects.filter(is_published=True).order_by('-date_uploaded')
        paginator = MagazinePagination()
        result_page = paginator.paginate_queryset(magazines, request)
        serializer = MagazineSerializer(result_page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    # def post(self, request):
    #     serializer = MagazineSerializer(data=request.data, context={'request': request})
    #     try:
    #         if serializer.is_valid():
    #             serializer.save()
    #             return Response(serializer.data, status=status.HTTP_201_CREATED)
    #         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    #     except DjangoValidationError as e:
    #         return Response(
    #             {"detail": " ".join(e.messages)},
    #             status=status.HTTP_429_TOO_MANY_REQUESTS
    #         )

@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class ArticleCreateAPIView(RateLimitHandlerMixin, generics.CreateAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)

            # ✅ Verify reCAPTCHA
            if not verify_recaptcha(serializer.validated_data['recaptcha_token']):
                return Response(
                    {"detail": "reCAPTCHA validation failed"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Remove token before saving to DB
            serializer.validated_data.pop('recaptcha_token')

            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except DjangoValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )


@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class SubscribeView(RateLimitHandlerMixin, APIView):
    def post(self, request):
        serializer = SubscriberSerializer(data=request.data)
        try:
            if serializer.is_valid():
                # Verify reCAPTCHA
                if not verify_recaptcha(serializer.validated_data['recaptcha_token']):
                    return Response(
                        {"detail": "reCAPTCHA validation failed"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Remove token before saving
                serializer.validated_data.pop('recaptcha_token')
                email = serializer.validated_data['email']
                subscriber, created = Subscriber.objects.update_or_create(
                    email=email,
                    defaults={'name': serializer.validated_data.get('name', '')}
                )
                message = 'Subscription updated' if not created else 'Successfully subscribed'
                return Response({'message': message}, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class CollaboratorCreateAPIView(RateLimitHandlerMixin, generics.CreateAPIView):
    queryset = Collaborator.objects.all()
    serializer_class = CollaboratorCreateSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            
            # Verify reCAPTCHA
            if not verify_recaptcha(serializer.validated_data['recaptcha_token']):
                return Response(
                    {"detail": "reCAPTCHA validation failed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Remove token before saving
            serializer.validated_data.pop('recaptcha_token')
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

@method_decorator(ratelimit(key='ip', rate='100/m', block=True), name='dispatch')
class LatestMagazineAPIView(RateLimitHandlerMixin, APIView):
    def get(self, request):
        latest = Magazine.objects.filter(is_published=True).order_by('-date_uploaded').first()
        if not latest:
            return Response({"detail": "No magazines found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = MagazineSerializer(latest, context={'request': request})
        return Response(serializer.data)
    

@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class ContactMessageCreateAPIView(RateLimitHandlerMixin, generics.CreateAPIView):
    """
    POST-only endpoint for users to send Contact Us messages.
    - Enforces max 3 'new' messages per email (via serializer + model clean).
    - Enforces DAILY_CREATION_LIMIT per day (via model clean).
    - Rate-limited to 5 requests/min per IP.
    """
    queryset = ContactMessage.objects.all()
    serializer_class = ContactMessageSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            
            # Verify reCAPTCHA
            if not verify_recaptcha(serializer.validated_data['recaptcha_token']):
                return Response(
                    {"detail": "reCAPTCHA validation failed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Remove token before saving
            serializer.validated_data.pop('recaptcha_token')
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            # catch model clean() errors (daily limit, etc.)
            return Response(
                {"detail": " ".join(e.messages)},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        

from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import SeasonalSubmissionConfig
from .serializers import SeasonalSubmissionConfigSerializer

@api_view(['GET'])
def active_season_api(request):
    """
    Get the active seasonal configuration
    """
    active_config = SeasonalSubmissionConfig.objects.filter(is_active=True).first()
    
    if active_config:
        serializer = SeasonalSubmissionConfigSerializer(active_config)
        return Response(serializer.data)
    else:
        return Response(
            {"error": "No active seasonal configuration found"},
            status=404
        )     

from django_ratelimit.decorators import ratelimit
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import AskSerializer
from woodtech.chatbot.services import ChatbotService
from woodtech.chatbot.token_service import TokenService
import json
import requests

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

@api_view(['POST'])
@ratelimit(key='ip', rate='30/m', block=True)
def ask_endpoint(request):
    ip = get_client_ip(request)
    
    # Initialize services
    chatbot_service = ChatbotService()
    token_service = TokenService()
    
    # Validate input
    serializer = AskSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    user_input = serializer.validated_data['prompt']
    previous_prompt = serializer.validated_data.get('previous_prompt', "")
    previous_answer = serializer.validated_data.get('previous_answer', "")
    
    # Check token limit initially
    if not token_service.check_token_limit(ip, 1000):  # Reserve some tokens for processing
        return Response(
            {'error': 'Daily token limit exceeded'}, 
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    try:
        # Step 1: Classifier Agent
        classifier_prompt = chatbot_service.get_classifier_prompt(
            previous_prompt, previous_answer, user_input
        )
        
        classifier_response = chatbot_service.gemini_service.call_api(
            classifier_prompt, 
            agent_type="classifier"
        )
        
        # Record classifier conversation
        chatbot_service.record_conversation(
            ip, user_input, "classifier", classifier_response, classifier_prompt
        )
        
        # Check tokens after classifier
        if not token_service.check_token_limit(ip, classifier_response['total_tokens'] + 1000):
            token_service.update_token_usage(ip, classifier_response['total_tokens'])
            return Response(
                {'error': 'Daily token limit exceeded during processing'}, 
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        relevant_urls = chatbot_service.validate_classifier_output(classifier_response['text'])
        context = chatbot_service.build_answer_context(relevant_urls)
        
        # Step 2: Answer Agent
        answer_prompt = chatbot_service.get_answer_prompt(
            previous_prompt, previous_answer, user_input, context
        )
        
        answer_response = chatbot_service.gemini_service.call_api(
            answer_prompt, 
            max_tokens=1500, 
            agent_type="answer"
        )
        
        # Record answer conversation
        chatbot_service.record_conversation(
            ip, user_input, "answer", answer_response, answer_prompt
        )
        
        # Update token usage
        total_tokens = classifier_response['total_tokens'] + answer_response['total_tokens']
        token_service.update_token_usage(ip, total_tokens)
        remaining_tokens = token_service.get_remaining_tokens(ip)
        
        # Process answer output
        cleaned_output = chatbot_service.clean_answer_output(answer_response['text'])
        
        try:
            result = json.loads(cleaned_output)
            if "supporting_paths" not in result:
                result["supporting_paths"] = []
            result["remaining_tokens"] = max(0, remaining_tokens)
            return Response(result)
        except json.JSONDecodeError:
            return Response({
                "answer": "I'm having trouble answering that. Please try a different question.",
                "supporting_paths": [],
                "remaining_tokens": max(0, remaining_tokens)
            })
    
    except requests.exceptions.RequestException as e:
        return Response(
            {'error': f'API error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# views.py
from .models import Banner
from .serializers import ActiveBannerSerializer

class ActiveBannerAPIView(APIView):
    """
    Simplified API endpoint to get only relevant banner display information
    """
    def get(self, request):
        try:
            active_banner = Banner.get_active_banner()
            
            if not active_banner:
                return Response(
                    {
                        "has_active_banner": False,
                        "banner": None
                    },
                    status=status.HTTP_200_OK
                )
            
            serializer = ActiveBannerSerializer(active_banner)
            return Response({
                "has_active_banner": True,
                "banner": serializer.data
            })
        
        except Exception as e:
            return Response(
                {
                    "detail": "An error occurred while fetching the active banner.",
                    "has_active_banner": False,
                    "banner": None
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )