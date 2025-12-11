# api_keys/authentication.py - UPDATED VERSION
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
from django.utils import timezone
import re
import structlog

from .models import APIKey

logger = structlog.get_logger(__name__)

class APIKeyAuthentication(authentication.BaseAuthentication):
    """API Key Authentication with Swagger exclusion"""
    
    # Paths that don't require API key authentication
    EXCLUDED_PATHS = [
        r'^/swagger/',
        r'^/swagger\.(json|yaml)$',
        r'^/redoc/',
        r'^/$',  # Health check
        r'^/auth/',  # Authentication endpoints
    ]
    
    def should_skip_auth(self, request):
        """Check if this path should skip API key authentication"""
        path = request.path
        for pattern in self.EXCLUDED_PATHS:
            if re.match(pattern, path):
                return True
        return False
    
    def authenticate(self, request):
        # Skip authentication for Swagger and public endpoints
        if self.should_skip_auth(request):
            return None  # Skip authentication entirely
        
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            # For API endpoints that require dual auth, return None
            # Let other authentication classes handle it
            return None
 
        try:
            api_key_obj = APIKey.objects.get(
                key=api_key,
                is_active=True
            )
            
            # Check if API key is expired
            if api_key_obj.is_expired:
                logger.warning("API key expired", key=api_key_obj.masked_key)
                raise AuthenticationFailed('API key has expired')
            
            # Update last used
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