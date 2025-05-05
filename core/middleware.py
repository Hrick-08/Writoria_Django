from django.utils.deprecation import MiddlewareMixin

class APITokenMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            request.api_token = request.session.get('api_token')
        else:
            request.api_token = None