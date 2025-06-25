import logging

from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.exceptions import ValidationError as DjangoValidationError
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited  # Add this import
from django.utils.decorators import method_decorator

from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from .models import Magazine, Article, Subscriber, Collaborator
from .serializers import (
    MagazineSerializer,
    ArticleSerializer,
    SubscriberSerializer,
    CollaboratorCreateSerializer
)

logger = logging.getLogger(__name__)


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
class MagazineListCreateAPIView(RateLimitHandlerMixin, APIView):
    def get(self, request):
        magazines = Magazine.objects.filter(is_published=True).order_by('-date_uploaded')
        paginator = MagazinePagination()
        result_page = paginator.paginate_queryset(magazines, request)
        serializer = MagazineSerializer(result_page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = MagazineSerializer(data=request.data, context={'request': request})
        try:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class ArticleCreateAPIView(RateLimitHandlerMixin, generics.CreateAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class SubscribeView(RateLimitHandlerMixin, APIView):
    def post(self, request):
        serializer = SubscriberSerializer(data=request.data)
        try:
            if serializer.is_valid():
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