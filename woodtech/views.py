from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from .models import Magazine
from .serializers import MagazineSerializer

class MagazinePagination(PageNumberPagination):
    page_size = 10  # You can change this as needed
    page_size_query_param = 'page_size'
    max_page_size = 100

class MagazineListCreateAPIView(APIView):
    def get(self, request):
        magazines = Magazine.objects.all().order_by('-date_uploaded')
        paginator = MagazinePagination()
        result_page = paginator.paginate_queryset(magazines, request)
        serializer = MagazineSerializer(result_page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = MagazineSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# articles/views.py

from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from .models import Article
from .serializers import ArticleSerializer

class ArticleCreateAPIView(generics.CreateAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
