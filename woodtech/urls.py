from django.urls import path
from .views import MagazineListCreateAPIView

urlpatterns = [
    path('magazines/', MagazineListCreateAPIView.as_view(), name='magazine-list-create'),
]
