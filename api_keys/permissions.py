from rest_framework import permissions
from django.utils import timezone
import structlog

logger = structlog.get_logger(__name__)

class HasPermission(permissions.BasePermission):
    """
    Custom permission to check API key permissions.
    For JWT users, always return True.
    For API keys, check if they have the required permission.
    """
    
    def __init__(self, required_permission):
        self.required_permission = required_permission
    
    def has_permission(self, request, view):
        # For JWT authenticated users, allow all permissions
        if request.auth and hasattr(request.auth, 'payload'):
            logger.debug("JWT user accessing endpoint", user_id=str(request.user.id))
            return True
        
        # For API key authentication
        if hasattr(request, 'auth') and request.auth:
            # Check if it's an API key object
            from .models import APIKey
            
            if isinstance(request.auth, APIKey):
                api_key = request.auth
                
                # Check permission
                has_perm = api_key.has_permission(self.required_permission)
                
                logger.debug(
                    "API key permission check",
                    key_id=str(api_key.id),
                    required_permission=self.required_permission,
                    has_permission=has_perm,
                    key_permissions=api_key.permissions
                )
                
                return has_perm
        
        # If neither JWT nor valid API key, deny access
        logger.warning("No valid authentication found for permission check")
        return False
    
    def __call__(self):
        return self