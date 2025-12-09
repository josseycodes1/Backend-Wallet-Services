import requests
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import api_view, permission_classes
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import structlog

from .serializers import (
    UserSerializer, 
    GoogleAuthSerializer, 
    TokenResponseSerializer,
    JWTTokenObtainSerializer
)

logger = structlog.get_logger(__name__)
User = get_user_model()

class GoogleAuthRedirectView(APIView):
    """Redirect to Google OAuth"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        google_auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={settings.GOOGLE_OAUTH_CLIENT_ID}&"
            f"redirect_uri={settings.GOOGLE_OAUTH_REDIRECT_URI}&"
            "response_type=code&"
            "scope=email profile&"
            "access_type=offline&"
            "prompt=consent"
        )
        logger.info("Redirecting to Google OAuth")
        return redirect(google_auth_url)

class GoogleAuthCallbackView(APIView):
    """Handle Google OAuth callback"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Google OAuth callback endpoint",
        query_serializer=GoogleAuthSerializer,
        responses={
            200: TokenResponseSerializer,
            400: "Bad Request"
        }
    )
    def get(self, request):
        code = request.GET.get('code')
        if not code:
            logger.warning("No code provided in Google callback")
            return Response(
                {"error": "Authorization code not provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Exchange code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'code': code,
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        
        try:
            token_response = requests.post(token_url, data=token_data)
            token_response.raise_for_status()
            token_json = token_response.json()
            access_token = token_json.get('access_token')
            
            # Get user info from Google
            user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {'Authorization': f'Bearer {access_token}'}
            user_info_response = requests.get(user_info_url, headers=headers)
            user_info_response.raise_for_status()
            user_info = user_info_response.json()
            
            # Get or create user
            email = user_info.get('email')
            google_id = user_info.get('id')
            first_name = user_info.get('given_name', '')
            last_name = user_info.get('family_name', '')
            picture = user_info.get('picture', '')
            
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'google_id': google_id,
                    'first_name': first_name,
                    'last_name': last_name,
                    'google_picture': picture,
                    'is_verified': True,
                    'username': email.split('@')[0]
                }
            )
            
            # Update user if not created
            if not created:
                user.google_id = google_id
                user.google_picture = picture
                user.first_name = first_name
                user.last_name = last_name
                user.is_verified = True
                user.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            serializer = TokenResponseSerializer({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            })
            
            logger.info("Google auth successful", email=email, created=created)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except requests.exceptions.RequestException as e:
            logger.error("Google OAuth error", error=str(e))
            return Response(
                {"error": "Google authentication failed"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error("Unexpected error in Google auth", error=str(e))
            return Response(
                {"error": "Authentication failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class JWTTokenObtainView(APIView):
    """Obtain JWT tokens with email/password (for testing)"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Obtain JWT tokens with email and password",
        request_body=JWTTokenObtainSerializer,
        responses={
            200: TokenResponseSerializer,
            400: "Bad Request"
        }
    )
    def post(self, request):
        serializer = JWTTokenObtainSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            
            response_serializer = TokenResponseSerializer({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            })
            
            logger.info("JWT token issued", email=user.email)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        
        logger.warning("JWT token request failed", errors=serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(generics.RetrieveUpdateAPIView):
    """Get or update user profile"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    @swagger_auto_schema(
        operation_description="Get current user profile",
        responses={200: UserSerializer}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_description="Update current user profile",
        request_body=UserSerializer,
        responses={200: UserSerializer}
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_description="Partial update current user profile",
        request_body=UserSerializer,
        responses={200: UserSerializer}
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)