from django.urls import path
from .views import MagazineListListAPIView, ArticleCreateAPIView, SubscribeView, get_csrf_token, CollaboratorCreateAPIView, LatestMagazineAPIView, health_check, ContactMessageCreateAPIView, ping_view, ask_endpoint, active_season_api, ActiveBannerAPIView, country_list

urlpatterns = [
    path('magazines/', MagazineListListAPIView.as_view(), name='magazine-list'),
    path('submit/', ArticleCreateAPIView.as_view(), name='article-submit'),
    path('subscribe/', SubscribeView.as_view(), name='subscribe'),
    path('collaborate/', CollaboratorCreateAPIView.as_view(), name='collaborator-create'),
    path('magazines/latest/', LatestMagazineAPIView.as_view(), name='latest-magazine'),
    path('contact/', ContactMessageCreateAPIView.as_view(), name='contact-message-create'),

    path('get-csrf/', get_csrf_token),
    path("health/", health_check, name="health-check"),
    path("ping/", ping_view, name="ping"),
    path('ask/', ask_endpoint, name='ask_endpoint'),
    path('seasonal/active/', active_season_api, name='active-season'),
    path('banner/active/', ActiveBannerAPIView.as_view(), name='active-banner'),
    path('countries/', country_list, name='country_list'),
]
