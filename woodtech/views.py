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

from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django_ratelimit.decorators import ratelimit
from .models import TokenUsage
from .serializers import AskSerializer
from .utils import (
    estimate_tokens, call_gemini_api, 
    CLASSIFIER_PROMPT, ANSWER_PROMPT, MAX_DAILY_TOKENS,
    build_answer_context, validate_classifier_output
)
import json
import requests

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

def update_token_usage(ip, tokens):
    try:
        with transaction.atomic():
            obj, created = TokenUsage.objects.select_for_update().get_or_create(
                ip_address=ip,
                defaults={'tokens_used': tokens, 'last_updated': timezone.now()}
            )
            if not created:
                if obj.last_updated < timezone.now() - timedelta(hours=24):
                    obj.tokens_used = tokens
                else:
                    obj.tokens_used += tokens
                obj.last_updated = timezone.now()
                obj.save()
        return obj.tokens_used
    except Exception as e:
        print(f"Database error: {str(e)}")
        return None

def get_current_usage(ip):
    try:
        obj = TokenUsage.objects.filter(
            ip_address=ip,
            last_updated__gte=timezone.now() - timedelta(hours=24)
        ).first()
        return obj.tokens_used if obj else 0
    except Exception as e:
        print(f"Database error: {str(e)}")
        return 0

@api_view(['POST'])
@ratelimit(key='ip', rate='30/m', block=True)
def ask_endpoint(request):
    ip = get_client_ip(request)
    current_usage = get_current_usage(ip)
    
    # Validate input
    serializer = AskSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    user_input = serializer.validated_data['prompt']
    previous_prompt = serializer.validated_data.get('previous_prompt', "")
    previous_answer = serializer.validated_data.get('previous_answer', "")
    
    user_tokens = estimate_tokens(user_input)
    
    # Check token limit
    if current_usage + user_tokens + 1000 > MAX_DAILY_TOKENS:
        return Response(
            {'error': 'Daily token limit exceeded'}, 
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    try:
        # Step 1: Find relevant sections
        classifier_prompt = (
            f"{CLASSIFIER_PROMPT}\n\n"
            f"PREVIOUS_QUESTION: {previous_prompt}\n"
            f"PREVIOUS_ANSWER: {previous_answer}\n"
            f"CURRENT_QUESTION: {user_input}\n"
        )
        classifier_tokens = estimate_tokens(classifier_prompt)
        
        if current_usage + classifier_tokens > MAX_DAILY_TOKENS:
            return Response(
                {'error': 'Daily token limit exceeded'}, 
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        classifier_response = call_gemini_api(classifier_prompt)
        classifier_output = classifier_response['candidates'][0]['content']['parts'][0]['text']
        actual_classifier_tokens = classifier_response.get('usageMetadata', {}).get('totalTokenCount', classifier_tokens)
        
        relevant_urls = validate_classifier_output(classifier_output)
        context = build_answer_context(relevant_urls)
        # print(context)

        today = datetime.now().strftime("%Y-%m-%d")

        
        # 🔹 Updated to include previous Q&A in prompt
        answer_prompt = (
            f"{ANSWER_PROMPT}\n\n"
            f"CURRENT_DATE: {today}\n"
            f"PREVIOUS_QUESTION: {previous_prompt}\n"
            f"PREVIOUS_ANSWER: {previous_answer}\n"
            f"CURRENT_QUESTION: {user_input}\n"
            f"CONTEXT:\n{context}"
        )

        # print(answer_prompt)
        answer_tokens = estimate_tokens(answer_prompt)
        
        if current_usage + actual_classifier_tokens + answer_tokens > MAX_DAILY_TOKENS:
            update_token_usage(ip, actual_classifier_tokens)
            return Response(
                {'error': 'Daily token limit exceeded during processing'}, 
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        answer_response = call_gemini_api(answer_prompt, max_tokens=1500)
        answer_output = answer_response['candidates'][0]['content']['parts'][0]['text']
        actual_answer_tokens = answer_response.get('usageMetadata', {}).get('totalTokenCount', answer_tokens)
        
        total_tokens = actual_classifier_tokens + actual_answer_tokens
        update_token_usage(ip, total_tokens)
        remaining_tokens = MAX_DAILY_TOKENS - (current_usage + total_tokens)
        
        import re
        cleaned_output = re.sub(r"^```(?:json)?|```$", "", answer_output.strip(), flags=re.MULTILINE)
        cleaned_output = "\n".join(
            line.split("|", 1)[-1].strip() if "|" in line else line
            for line in cleaned_output.splitlines()
        )
        # print(cleaned_output)
        
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