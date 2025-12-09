from django.shortcuts import get_object_or_404
from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import structlog

from .models import APIKey
from .serializers import (
    APIKeySerializer,
    CreateAPIKeySerializer,
    APIKeyResponseSerializer,
    RolloverAPIKeySerializer,
    RevokeAPIKeySerializer,
    UpdateAPIKeySerializer
)

logger = structlog.get_logger(__name__)

class APIKeyListView(generics.ListAPIView):
    """List all API keys for the authenticated user"""
    serializer_class = APIKeySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user).order_by('-created_at')
    
    @swagger_auto_schema(
        operation_description="List all API keys for the authenticated user",
        responses={200: APIKeySerializer(many=True)},
        security=[{'Bearer': []}]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class CreateAPIKeyView(APIView):
    """Create a new API key"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Create a new API key",
        request_body=CreateAPIKeySerializer,
        responses={
            201: APIKeyResponseSerializer,
            400: "Bad Request"
        },
        security=[{'Bearer': []}]
    )
    def post(self, request):
        serializer = CreateAPIKeySerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(
                "API key creation validation failed",
                errors=serializer.errors,
                user_id=str(request.user.id)
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Create API key
        name = serializer.validated_data['name']
        permissions = serializer.validated_data['permissions']
        expiry_string = serializer.validated_data['expiry']
        
        # Calculate expiry date
        expires_at = APIKey.get_expiry_date(expiry_string)
        
        # Create API key
        api_key = APIKey.objects.create(
            user=request.user,
            name=name,
            permissions=permissions,
            expires_at=expires_at
        )
        
        response_serializer = APIKeyResponseSerializer({
            'api_key': api_key.key,
            'expires_at': api_key.expires_at,
            'name': api_key.name,
            'permissions': api_key.permissions
        })
        
        logger.info(
            "API key created",
            key_id=str(api_key.id),
            user_id=str(request.user.id),
            name=name,
            permissions=permissions
        )
        
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

class RolloverAPIKeyView(APIView):
    """Rollover an expired API key"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Rollover an expired API key with new expiry",
        request_body=RolloverAPIKeySerializer,
        responses={
            200: APIKeyResponseSerializer,
            400: "Bad Request",
            404: "API key not found"
        },
        security=[{'Bearer': []}]
    )
    def post(self, request):
        serializer = RolloverAPIKeySerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(
                "API key rollover validation failed",
                errors=serializer.errors,
                user_id=str(request.user.id)
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        api_key = serializer.validated_data['api_key']
        expiry_string = serializer.validated_data['expiry']
        
        # Rollover the key
        try:
            new_api_key = api_key.rollover(expiry_string)
            
            response_serializer = APIKeyResponseSerializer({
                'api_key': new_api_key.key,
                'expires_at': new_api_key.expires_at,
                'name': new_api_key.name,
                'permissions': new_api_key.permissions
            })
            
            logger.info(
                "API key rolled over",
                old_key_id=str(api_key.id),
                new_key_id=str(new_api_key.id),
                user_id=str(request.user.id)
            )
            
            return Response(response_serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(
                "API key rollover failed",
                error=str(e),
                key_id=str(api_key.id),
                user_id=str(request.user.id)
            )
            
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class RevokeAPIKeyView(APIView):
    """Revoke/delete an API key"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Revoke/delete an API key",
        request_body=RevokeAPIKeySerializer,
        responses={
            200: {'detail': 'API key revoked successfully'},
            400: "Bad Request",
            404: "API key not found"
        },
        security=[{'Bearer': []}]
    )
    def post(self, request):
        serializer = RevokeAPIKeySerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning(
                "API key revocation validation failed",
                errors=serializer.errors,
                user_id=str(request.user.id)
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        api_key = serializer.validated_data['api_key']
        
        # Check if this is the only active key
        active_keys = APIKey.objects.filter(
            user=request.user,
            is_active=True
        ).exclude(id=api_key.id).count()
        
        if active_keys == 0 and api_key.is_active:
            return Response(
                {'error': 'Cannot revoke the only active API key'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Deactivate the key
        api_key.is_active = False
        api_key.save(update_fields=['is_active', 'updated_at'])
        
        logger.info(
            "API key revoked",
            key_id=str(api_key.id),
            user_id=str(request.user.id)
        )
        
        return Response(
            {'detail': 'API key revoked successfully'},
            status=status.HTTP_200_OK
        )

class UpdateAPIKeyView(generics.UpdateAPIView):
    """Update API key (name, active status)"""
    serializer_class = UpdateAPIKeySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user)
    
    @swagger_auto_schema(
        operation_description="Update API key details",
        request_body=UpdateAPIKeySerializer,
        responses={
            200: APIKeySerializer,
            400: "Bad Request",
            404: "API key not found"
        },
        security=[{'Bearer': []}]
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)
