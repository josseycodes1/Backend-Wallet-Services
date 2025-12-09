from django.utils.deprecation import MiddlewareMixin
import time
import structlog

from .models import APIKeyUsageLog

logger = structlog.get_logger(__name__)

class APIKeyMiddleware(MiddlewareMixin):
    """Middleware to log API key usage"""
    
    def process_request(self, request):
        # Store start time for duration calculation
        request._api_key_start_time = time.time()
        
        # Get API key from header
        api_key_value = request.headers.get('X-API-Key')
        
        if api_key_value:
            try:
                from .models import APIKey
                api_key = APIKey.objects.get(key=api_key_value)
                request.api_key_obj = api_key
            except APIKey.DoesNotExist:
                request.api_key_obj = None
    
    def process_response(self, request, response):
        # Log API key usage if an API key was used
        if hasattr(request, 'api_key_obj') and request.api_key_obj:
            # Calculate duration
            start_time = getattr(request, '_api_key_start_time', None)
            duration_ms = 0
            
            if start_time:
                duration_ms = int((time.time() - start_time) * 1000)
            
            # Create usage log
            try:
                APIKeyUsageLog.objects.create(
                    api_key=request.api_key_obj,
                    endpoint=request.path,
                    method=request.method,
                    status_code=response.status_code,
                    request_data={
                        'params': dict(request.GET),
                        'data': request.POST.dict() if request.POST else {},
                        'headers': {k: v for k, v in request.headers.items() 
                                  if k.lower() not in ['authorization', 'x-api-key']}
                    },
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    duration_ms=duration_ms
                )
                
                logger.debug(
                    "API key usage logged",
                    key_id=str(request.api_key_obj.id),
                    endpoint=request.path,
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms
                )
                
            except Exception as e:
                logger.error("Failed to log API key usage", error=str(e))
        
        return response
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip