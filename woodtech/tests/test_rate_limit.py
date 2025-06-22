from django.test import TestCase
from rest_framework.test import APITestCase, APIRequestFactory
from django_ratelimit.exceptions import Ratelimited
from django.core.cache import cache
from ..models import Magazine, Article, Subscriber, Collaborator
from ..views import (
    health_check,
    MagazineListCreateAPIView,
    ArticleCreateAPIView,
    SubscribeView,
    CollaboratorCreateAPIView,
    LatestMagazineAPIView
)

class RateLimitTests(APITestCase):
    def setUp(self):
        # Clear cache before each test
        cache.clear()
        self.factory = APIRequestFactory()
        
        # Create test data
        self.magazine = Magazine.objects.create(
            title="Test Magazine",
            is_published=True
        )
        self.article_data = {
            "title": "Test Article",
            "content": "Test content",
            "magazine": self.magazine.id
        }
        self.subscriber_data = {"email": "test@example.com", "name": "Test User"}
        self.collaborator_data = {"name": "Test Collaborator", "email": "collab@example.com"}

    def test_health_check_rate_limit(self):
        """Test health check endpoint rate limiting (30 requests/min)"""
        view = health_check
        url = '/health/'
        
        # Make 30 requests (should all succeed)
        for _ in range(30):
            request = self.factory.get(url)
            response = view(request)
            self.assertEqual(response.status_code, 200)
        
        # 31st request should be rate limited
        request = self.factory.get(url)
        response = view(request)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data['detail'], "Too many requests. Please try again later.")

    def test_magazine_list_rate_limit(self):
        """Test magazine list endpoint rate limiting (20 requests/min)"""
        view = MagazineListCreateAPIView.as_view()
        url = '/api/magazines/'
        
        # Make 20 requests
        for _ in range(20):
            request = self.factory.get(url)
            response = view(request)
            self.assertEqual(response.status_code, 200)
        
        # 21st request should be rate limited
        request = self.factory.get(url)
        response = view(request)
        self.assertEqual(response.status_code, 429)

    def test_magazine_create_rate_limit(self):
        """Test magazine create endpoint rate limiting (20 requests/min)"""
        view = MagazineListCreateAPIView.as_view()
        url = '/api/magazines/'
        data = {"title": "New Magazine", "is_published": True}
        
        # Make 20 requests
        for _ in range(20):
            request = self.factory.post(url, data)
            response = view(request)
            self.assertIn(response.status_code, [201, 400])  # 400 if validation fails
        
        # 21st request should be rate limited
        request = self.factory.post(url, data)
        response = view(request)
        self.assertEqual(response.status_code, 429)

    def test_article_create_rate_limit(self):
        """Test article create endpoint rate limiting (5 requests/min)"""
        view = ArticleCreateAPIView.as_view()
        url = '/api/articles/'
        
        # Make 5 requests
        for _ in range(5):
            request = self.factory.post(url, self.article_data)
            response = view(request)
            self.assertIn(response.status_code, [201, 400])
        
        # 6th request should be rate limited
        request = self.factory.post(url, self.article_data)
        response = view(request)
        self.assertEqual(response.status_code, 429)

    def test_subscribe_rate_limit(self):
        """Test subscription endpoint rate limiting (10 requests/min)"""
        view = SubscribeView.as_view()
        url = '/api/subscribe/'
        
        # Make 10 requests
        for _ in range(10):
            request = self.factory.post(url, self.subscriber_data)
            response = view(request)
            self.assertIn(response.status_code, [201, 400])
        
        # 11th request should be rate limited
        request = self.factory.post(url, self.subscriber_data)
        response = view(request)
        self.assertEqual(response.status_code, 429)

    def test_collaborator_create_rate_limit(self):
        """Test collaborator endpoint rate limiting (5 requests/min)"""
        view = CollaboratorCreateAPIView.as_view()
        url = '/api/collaborators/'
        
        # Make 5 requests
        for _ in range(5):
            request = self.factory.post(url, self.collaborator_data)
            response = view(request)
            self.assertIn(response.status_code, [201, 400])
        
        # 6th request should be rate limited
        request = self.factory.post(url, self.collaborator_data)
        response = view(request)
        self.assertEqual(response.status_code, 429)

    def test_latest_magazine_rate_limit(self):
        """Test latest magazine endpoint rate limiting (20 requests/min)"""
        view = LatestMagazineAPIView.as_view()
        url = '/api/magazines/latest/'
        
        # Make 20 requests
        for _ in range(20):
            request = self.factory.get(url)
            response = view(request)
            self.assertIn(response.status_code, [200, 404])
        
        # 21st request should be rate limited
        request = self.factory.get(url)
        response = view(request)
        self.assertEqual(response.status_code, 429)

    def test_different_ips_not_rate_limited(self):
        """Test that different IPs have separate rate limits"""
        view = SubscribeView.as_view()
        url = '/api/subscribe/'
        
        # Make 10 requests from IP 1.1.1.1
        for _ in range(10):
            request = self.factory.post(url, self.subscriber_data, REMOTE_ADDR='1.1.1.1')
            response = view(request)
            self.assertIn(response.status_code, [201, 400])
        
        # First request from IP 2.2.2.2 should still work
        request = self.factory.post(url, self.subscriber_data, REMOTE_ADDR='2.2.2.2')
        response = view(request)
        self.assertIn(response.status_code, [201, 400])
        
        # Next request from IP 1.1.1.1 should be rate limited
        request = self.factory.post(url, self.subscriber_data, REMOTE_ADDR='1.1.1.1')
        response = view(request)
        self.assertEqual(response.status_code, 429)