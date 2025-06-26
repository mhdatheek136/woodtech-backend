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


# myapp/signals.py

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from .models import Collaborator, Article

@receiver(post_delete, sender=Collaborator)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    if instance.logo_or_sample:
        instance.logo_or_sample.delete(save=False)

@receiver(pre_save, sender=Collaborator)
def auto_delete_old_file_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return  # new object, no old file to delete

    try:
        old_file = Collaborator.objects.get(pk=instance.pk).logo_or_sample
    except Collaborator.DoesNotExist:
        return

    new_file = instance.logo_or_sample
    if old_file and old_file != new_file:
        old_file.delete(save=False)


@receiver(post_delete, sender=Article)
def auto_delete_article_file_on_delete(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)

@receiver(pre_save, sender=Article)
def auto_delete_old_article_file_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_file = Article.objects.get(pk=instance.pk).file
    except Article.DoesNotExist:
        return

    new_file = instance.file
    if old_file and old_file != new_file:
        old_file.delete(save=False)
