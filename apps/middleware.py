from django.http import JsonResponse


class HealthCheckMiddleware:
    """Answer /healthz/ before host validation so container probes on 127.0.0.1 work with strict ALLOWED_HOSTS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/healthz/':
            return JsonResponse({'status': 'ok'})
        return self.get_response(request)
