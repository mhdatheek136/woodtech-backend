from django.urls import path
from .views import MagazineListCreateAPIView, ArticleCreateAPIView, SubscribeView

urlpatterns = [
    path('magazines/', MagazineListCreateAPIView.as_view(), name='magazine-list-create'),
    path('submit/', ArticleCreateAPIView.as_view(), name='article-submit'),
    path('subscribe/', SubscribeView.as_view(), name='subscribe'),
]
