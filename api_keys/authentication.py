from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
from django.utils import timezone
import structlog

from .models import APIKey

logger = structlog.get_logger(__name__)

class APIKeyAuthentication(authentication.BaseAuthentication):
    """API Key Authentication"""
    
    def authenticate(self, request):
   
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return None
 
        try:
            api_key_obj = APIKey.objects.get(
                key=api_key,
                is_active=True
            )
            
           
            if api_key_obj.is_expired:
                logger.warning("API key expired", key=api_key_obj.masked_key)
                raise AuthenticationFailed('API key has expired')
            
           
            api_key_obj.update_last_used()
            
            logger.debug(
                "API key authentication successful",
                user_id=str(api_key_obj.user.id),
                key_name=api_key_obj.name
            )
            
            return (api_key_obj.user, api_key_obj)
            
        except APIKey.DoesNotExist:
            logger.warning("Invalid API key attempted", key=api_key[:10] + "..." if api_key else "None")
            raise AuthenticationFailed('Invalid API key')
        except Exception as e:
            logger.error("API key authentication error", error=str(e))
            raise AuthenticationFailed('Authentication failed')
    
    def authenticate_header(self, request):
        return 'APIKey'