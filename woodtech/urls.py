from django.urls import path
from .views import MagazineListCreateAPIView, ArticleCreateAPIView, SubscribeView, get_csrf_token, CollaboratorCreateAPIView, LatestMagazineAPIView, health_check, ContactMessageCreateAPIView

urlpatterns = [
    path('magazines/', MagazineListCreateAPIView.as_view(), name='magazine-list-create'),
    path('submit/', ArticleCreateAPIView.as_view(), name='article-submit'),
    path('subscribe/', SubscribeView.as_view(), name='subscribe'),
    path('collaborate/', CollaboratorCreateAPIView.as_view(), name='collaborator-create'),
    path('magazines/latest/', LatestMagazineAPIView.as_view(), name='latest-magazine'),
    path('contact/', ContactMessageCreateAPIView.as_view(), name='contact-message-create'),

    path('get-csrf/', get_csrf_token),
    path("health/", health_check, name="health-check"),
]
