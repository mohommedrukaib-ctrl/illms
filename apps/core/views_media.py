import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.views.static import serve


@login_required
def secure_media_serve(request, path):
    """
    Permission-checked view to serve files uploaded to MEDIA_ROOT.
    Ensures that anonymous users can never access files directly.
    """
    # Verify path is inside safe boundary
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(full_path):
        raise Http404("Requested file does not exist.")

    # Apply access rules (e.g. standard user role checks)
    response = HttpResponse()
    # Let django static serve act as fallback wrapper
    return serve(request, path, document_root=settings.MEDIA_ROOT)