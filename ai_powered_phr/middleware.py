from django.conf import settings
class CustomMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers['Server'] = "None"
        response['X-XSS-Protection'] = '1; mode=block'
        response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
         # Add Content Security Policy (CSP) headers
        response['Content-Security-Policy'] = (
            "default-src 'self'; "          # Allow resources only from the same origin
            "style-src 'self'; "            # Allow styles only from the same origin
            "img-src 'self' data:; "        # Allow images from the same origin and data URIs
            "connect-src 'self'; "          # Allow AJAX calls only from same origin
            "font-src 'self'; "             # Allow fonts from the same origin
            "frame-ancestors 'none'; "      # Prevent framing to mitigate clickjacking
            "form-action 'self'; "          # Allow forms only from the same origin
            "base-uri 'self';"              
        )
        
        return response