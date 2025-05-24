from django.urls import path
from .views import MagazineListCreateAPIView, ArticleCreateAPIView, SubscribeView, get_csrf_token

urlpatterns = [
    path('magazines/', MagazineListCreateAPIView.as_view(), name='magazine-list-create'),
    path('submit/', ArticleCreateAPIView.as_view(), name='article-submit'),
    path('subscribe/', SubscribeView.as_view(), name='subscribe'),

    path('csrf/', get_csrf_token),
]
