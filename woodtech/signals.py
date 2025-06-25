from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.core.files.storage import default_storage
from .models import Magazine

@receiver(post_delete, sender=Magazine)
def auto_delete_files_on_delete(sender, instance, **kwargs):
    # Delete PDF file from storage
    if instance.pdf_file:
        instance.pdf_file.delete(save=False)

    # Delete cover image from storage
    if instance.cover_image:
        instance.cover_image.delete(save=False)

    # Delete each page image from S3
    if instance.page_images:
        for url in instance.page_images:
            # Get the relative path from the full S3 URL
            relative_path = url.split(f'/{default_storage.location}/')[-1]
            if default_storage.exists(relative_path):
                default_storage.delete(relative_path)
