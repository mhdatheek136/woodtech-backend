# woodtech/signals.py

import os
import shutil
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Magazine

@receiver(post_delete, sender=Magazine)
def auto_delete_files_on_delete(sender, instance, **kwargs):
    # Delete PDF file
    if instance.pdf_file and os.path.isfile(instance.pdf_file.path):
        os.remove(instance.pdf_file.path)

    # Delete cover image
    if instance.cover_image and os.path.isfile(instance.cover_image.path):
        os.remove(instance.cover_image.path)

    # Delete generated page images folder
    folder_name = f"vol{instance.volume_number}_issue{instance.season_number}"
    pages_folder = os.path.join(settings.MEDIA_ROOT, 'magazines', 'pages', folder_name)
    if os.path.isdir(pages_folder):
        shutil.rmtree(pages_folder)
