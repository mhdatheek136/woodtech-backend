# woodtech/middleware.py
from django.http import JsonResponse
from django_ratelimit.exceptions import Ratelimited

class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    def process_exception(self, request, exception):
        if isinstance(exception, Ratelimited):
            return JsonResponse(
                {
                    "status": "error",
                    "code": 429,
                    "message": "Too many requests. Please try again later."
                },
                status=429
            )
        return None