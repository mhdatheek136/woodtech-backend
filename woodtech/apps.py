from django.apps import AppConfig


class WoodtechConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'woodtech'

    def ready(self):
        import woodtech.signals 
