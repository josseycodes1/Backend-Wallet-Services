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
        
        if request.auth and hasattr(request.auth, 'payload'):
            logger.debug("JWT user accessing endpoint", user_id=str(request.user.id))
            return True
        
       
        if hasattr(request, 'auth') and request.auth:
            
            from .models import APIKey
            
            if isinstance(request.auth, APIKey):
                api_key = request.auth
                
                
                has_perm = api_key.has_permission(self.required_permission)
                
                logger.debug(
                    "API key permission check",
                    key_id=str(api_key.id),
                    required_permission=self.required_permission,
                    has_permission=has_perm,
                    key_permissions=api_key.permissions
                )
                
                return has_perm
        
        
        logger.warning("No valid authentication found for permission check")
        return False
    
    def __call__(self):
        return self
    
class RequireBothJWTAuthAndAPIKeyPermission(permissions.BasePermission):
    """
    Simple permission that requires BOTH JWT AND API Key
    """
    
    def has_permission(self, request, view):
        
        if not request.user.is_authenticated:
            return False
        
        
        api_key_header = request.headers.get('X-API-Key')
        if not api_key_header:
            return False
        
       
        from .models import APIKey
        try:
            api_key = APIKey.objects.get(
                key=api_key_header,
                is_active=True,
                user=request.user
            )
            
           
            if api_key.is_expired:
                return False
            
            
            if 'deposit' in request.path:
                if not api_key.has_permission('deposit'):
                    return False
            elif 'transfer' in request.path:
                if not api_key.has_permission('transfer'):
                    return False
            elif 'balance' in request.path or 'transactions' in request.path:
                if not api_key.has_permission('read'):
                    return False
            
            api_key.update_last_used()
            return True
            
        except APIKey.DoesNotExist:
            return False