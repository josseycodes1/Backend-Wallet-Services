from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
import structlog

logger = structlog.get_logger(__name__)
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'google_picture', 'is_verified', 'created_at']
        read_only_fields = ['id', 'is_verified', 'created_at']

class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['user', 'phone_number', 'address', 'date_of_birth', 'country', 'currency']
        read_only_fields = ['user']

class GoogleAuthSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    
    def validate(self, attrs):
        logger.info("Validating Google auth code")
        return attrs
    
class GoogleAuthURLSerializer(serializers.Serializer):
    """Serializer for Google OAuth URL response"""
    auth_url = serializers.CharField()
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass

class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
    wallet = serializers.DictField() 
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass

class JWTTokenObtainSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        try:
            user = User.objects.get(email=email)
            if not user.check_password(password):
                logger.warning("Invalid password for user", email=email)
                raise serializers.ValidationError("Invalid credentials")
        except User.DoesNotExist:
            logger.warning("User not found", email=email)
            raise serializers.ValidationError("Invalid credentials")
        
        attrs['user'] = user
        return attrs