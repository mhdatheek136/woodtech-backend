from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from woodtech.models import TokenUsage

class TokenService:
    def __init__(self, max_daily_tokens=50000):
        self.max_daily_tokens = max_daily_tokens

    def update_token_usage(self, ip, tokens):
        try:
            with transaction.atomic():
                obj, created = TokenUsage.objects.select_for_update().get_or_create(
                    ip_address=ip,
                    defaults={'tokens_used': tokens, 'last_updated': timezone.now()}
                )
                if not created:
                    if obj.last_updated < timezone.now() - timedelta(hours=24):
                        obj.tokens_used = tokens
                    else:
                        obj.tokens_used += tokens
                    obj.last_updated = timezone.now()
                    obj.save()
            return obj.tokens_used
        except Exception as e:
            print(f"Database error: {str(e)}")
            return None

    def get_current_usage(self, ip):
        try:
            obj = TokenUsage.objects.filter(
                ip_address=ip,
                last_updated__gte=timezone.now() - timedelta(hours=24)
            ).first()
            return obj.tokens_used if obj else 0
        except Exception as e:
            print(f"Database error: {str(e)}")
            return 0

    def check_token_limit(self, ip, additional_tokens=0):
        current_usage = self.get_current_usage(ip)
        return current_usage + additional_tokens <= self.max_daily_tokens

    def get_remaining_tokens(self, ip):
        current_usage = self.get_current_usage(ip)
        return max(0, self.max_daily_tokens - current_usage)