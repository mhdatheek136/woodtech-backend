from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework import generics

from .models import Magazine, Article, Subscriber
from .serializers import MagazineSerializer, ArticleSerializer, SubscriberSerializer

from utils.recaptcha import verify_recaptcha

from functools import wraps

# views.py
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse

# views.py
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse

@ensure_csrf_cookie
def get_csrf_token(request):
    return JsonResponse({"message": "CSRF cookie set"})




def recaptcha_required(view_func):
    @wraps(view_func)
    def wrapped(self, request, *args, **kwargs):
        token = request.data.get('recaptcha_token')
        if not token or not verify_recaptcha(token):
            return Response({'error': 'Invalid reCAPTCHA. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)
        return view_func(self, request, *args, **kwargs)
    return wrapped


class MagazinePagination(PageNumberPagination):
    page_size = 10  # Adjust as needed
    page_size_query_param = 'page_size'
    max_page_size = 100


class MagazineListCreateAPIView(APIView):
    def get(self, request):
        magazines = Magazine.objects.all().order_by('-date_uploaded')
        paginator = MagazinePagination()
        result_page = paginator.paginate_queryset(magazines, request)
        serializer = MagazineSerializer(result_page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    @recaptcha_required
    def post(self, request):
        serializer = MagazineSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ArticleCreateAPIView(generics.CreateAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer

    @recaptcha_required
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)


class SubscribeView(APIView):
    @recaptcha_required
    def post(self, request):
        serializer = SubscriberSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data.get('email')

            # Delete older subscriber with the same email
            Subscriber.objects.filter(email=email).delete()

            # Save new subscriber
            serializer.save()
            return Response({'message': 'Successfully subscribed'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
