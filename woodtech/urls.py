from django.urls import path
from .views import MagazineListCreateAPIView, ArticleCreateAPIView

urlpatterns = [
    path('magazines/', MagazineListCreateAPIView.as_view(), name='magazine-list-create'),
    path('submit/', ArticleCreateAPIView.as_view(), name='article-submit'),
]
