from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Magazine
from .serializers import MagazineSerializer

class MagazineListCreateAPIView(APIView):
    def get(self, request):
        magazines = Magazine.objects.all().order_by('-date_uploaded')
        serializer = MagazineSerializer(magazines, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = MagazineSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
