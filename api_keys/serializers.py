from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from .models import APIKey
import structlog

logger = structlog.get_logger(__name__)

class APIKeySerializer(serializers.ModelSerializer):
    masked_key = serializers.CharField(read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = APIKey
        fields = [
            'id', 'name', 'masked_key', 'permissions', 'is_active',
            'expires_at', 'last_used_at', 'created_at', 'updated_at',
            'is_valid', 'is_expired'
        ]
        read_only_fields = [
            'id', 'masked_key', 'expires_at', 'last_used_at',
            'created_at', 'updated_at', 'is_valid', 'is_expired'
        ]

class CreateAPIKeySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=True)
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=['read', 'deposit', 'transfer']),
        required=True
    )
    expiry = serializers.ChoiceField(
        choices=['1H', '1D', '1M', '1Y'],
        required=True
    )
    
    def validate(self, attrs):
        user = self.context['request'].user
        
        # Check max API keys per user
        active_keys_count = APIKey.objects.filter(
            user=user,
            is_active=True
        ).count()
        
        if active_keys_count >= settings.MAX_API_KEYS_PER_USER:
            raise serializers.ValidationError(
                f"Maximum {settings.MAX_API_KEYS_PER_USER} active API keys allowed per user"
            )
        
        # Validate permissions
        permissions = attrs['permissions']
        valid_permissions = ['read', 'deposit', 'transfer']
        
        for perm in permissions:
            if perm not in valid_permissions:
                raise serializers.ValidationError(
                    f"Invalid permission: {perm}. Valid permissions are: {valid_permissions}"
                )
        
        return attrs

class APIKeyResponseSerializer(serializers.Serializer):
    api_key = serializers.CharField()
    expires_at = serializers.DateTimeField()
    name = serializers.CharField()
    permissions = serializers.ListField()
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass

class RolloverAPIKeySerializer(serializers.Serializer):
    expired_key_id = serializers.UUIDField(required=True)
    expiry = serializers.ChoiceField(
        choices=['1H', '1D', '1M', '1Y'],
        required=True
    )
    
    def validate(self, attrs):
        user = self.context['request'].user
        key_id = attrs['expired_key_id']
        
        try:
            api_key = APIKey.objects.get(id=key_id, user=user)
            
            # Check if key is expired
            if not api_key.is_expired:
                raise serializers.ValidationError("Cannot rollover non-expired key")
            
            attrs['api_key'] = api_key
            return attrs
            
        except APIKey.DoesNotExist:
            raise serializers.ValidationError("API key not found or you don't have permission")

class RevokeAPIKeySerializer(serializers.Serializer):
    key_id = serializers.UUIDField(required=True)
    
    def validate(self, attrs):
        user = self.context['request'].user
        key_id = attrs['key_id']
        
        try:
            api_key = APIKey.objects.get(id=key_id, user=user)
            attrs['api_key'] = api_key
            return attrs
            
        except APIKey.DoesNotExist:
            raise serializers.ValidationError("API key not found or you don't have permission")

class UpdateAPIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ['name', 'is_active']
    
    def update(self, instance, validated_data):
        # Don't allow deactivating if it's the only active key
        if 'is_active' in validated_data and not validated_data['is_active']:
            active_keys = APIKey.objects.filter(
                user=instance.user,
                is_active=True
            ).exclude(id=instance.id).count()
            
            if active_keys == 0:
                raise serializers.ValidationError(
                    "Cannot deactivate the only active API key"
                )
        
        return super().update(instance, validated_data)