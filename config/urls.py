from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.utils import timezone
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from django.http import JsonResponse

def health_check(request):
    try:
        response_data = {
            'status': 'healthy',
            'service': 'Wallet Service API',
            'version': '1.0.0',
            'timestamp': timezone.now().isoformat()
        }
        return JsonResponse(response_data)
    except Exception as e:
       
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


schema_view = get_schema_view(
    openapi.Info(
        title="Wallet Service API",
        default_version='v1',
        description="Wallet Service with Paystack, JWT & API Keys",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@walletservice.local"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
   
    path('admin/', admin.site.urls),
    path('', health_check, name='health-check'),
    
  
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    
    path('auth/', include('users.urls')),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    
    path('wallet/', include('wallet.urls')),
    

    path('keys/', include('api_keys.urls')),
]