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
from django.utils import timezone

from .serializers import (
    UserSerializer, 
    GoogleAuthSerializer, 
    TokenResponseSerializer,
    JWTTokenObtainSerializer
)

logger = structlog.get_logger(__name__)
User = get_user_model()

class GoogleAuthRedirectView(APIView):
    """Get Google OAuth URL for authentication"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Get Google OAuth URL for authentication",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'google_auth_url': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Google OAuth authorization URL"
                    )
                }
            ),
            400: "Invalid OAuth configuration"
        }
    )
    def get(self, request):
        try:
            
            if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
                logger.error("Google OAuth not properly configured")
                return Response(
                    {"error": "Google OAuth configuration missing"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            
            google_auth_url = (
                "https://accounts.google.com/o/oauth2/v2/auth?"
                f"client_id={settings.GOOGLE_OAUTH_CLIENT_ID}&"
                f"redirect_uri={settings.GOOGLE_OAUTH_REDIRECT_URI}&"
                "response_type=code&"
                "scope=email%20profile&"  
                "access_type=offline&"
                "prompt=consent"
            )
            
            logger.info("Google OAuth URL generated")
            
            
            accept_header = request.headers.get('Accept', '')
            
            if 'application/json' in accept_header or request.GET.get('format') == 'json':
                
                return Response({
                    'google_auth_url': google_auth_url,
                    'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                    'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI
                }, status=status.HTTP_200_OK)
            else:
               
                return redirect(google_auth_url)
                
        except Exception as e:
            logger.error(f"Error generating Google auth URL: {str(e)}")
            return Response(
                {"error": "Failed to generate authentication URL"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class GoogleAuthCallbackView(APIView):
    """Handle Google OAuth callback"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Google OAuth callback endpoint",
        query_serializer=GoogleAuthSerializer,
        responses={
            200: TokenResponseSerializer,
            400: "Bad Request - Missing code or Google returned error",
            401: "Unauthorized - Invalid or expired authorization code",
            500: "Internal Server Error - Google API error or server error"
        }
    )
    def get(self, request):
        code = request.GET.get('code')
        error = request.GET.get('error')
        error_description = request.GET.get('error_description')
        
        
        if error:
            logger.warning(
                "Google OAuth error returned",
                error=error,
                error_description=error_description
            )
            return Response(
                {
                    "error": f"Google authentication failed: {error}",
                    "details": error_description or "No additional details provided by Google"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
       
        if not code:
            logger.warning("No authorization code provided in callback")
            return Response(
                {
                    "error": "Authorization code is required",
                    "details": "The 'code' parameter is missing from the Google callback URL"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                'code': code,
                'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
                'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
                'grant_type': 'authorization_code'
            }
            
            token_response = requests.post(token_url, data=token_data)
            
            
            if token_response.status_code != 200:
                error_data = token_response.json()
                logger.warning(
                    "Failed to exchange code for token",
                    status_code=token_response.status_code,
                    error=error_data
                )
                return Response(
                    {
                        "error": "Failed to exchange authorization code for tokens",
                        "details": error_data.get('error_description', 'Invalid authorization code'),
                        "google_error": error_data.get('error')
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            token_json = token_response.json()
            access_token = token_json.get('access_token')
            
            
            user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {'Authorization': f'Bearer {access_token}'}
            user_info_response = requests.get(user_info_url, headers=headers)
            
            
            if user_info_response.status_code != 200:
                logger.warning(
                    "Failed to fetch user info from Google",
                    status_code=user_info_response.status_code
                )
                return Response(
                    {
                        "error": "Failed to retrieve user information from Google",
                        "details": "Google API returned an error when fetching user profile"
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            user_info = user_info_response.json()
            
           
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
            
            
            if not created:
                user.google_id = google_id
                user.google_picture = picture
                user.first_name = first_name
                user.last_name = last_name
                user.is_verified = True
                user.save()
            
           
            refresh = RefreshToken.for_user(user)
            
            serializer = TokenResponseSerializer({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            })
            
            logger.info(
                "Google auth successful",
                email=email,
                created=created,
                user_id=str(user.id)
            )
            
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except requests.exceptions.RequestException as e:
            logger.error("Network error in Google auth", error=str(e))
            return Response(
                {
                    "error": "Network error during Google authentication",
                    "details": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error("Unexpected error in Google auth", error=str(e), exc_info=True)
            return Response(
                {
                    "error": "Authentication failed due to an unexpected error",
                    "details": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
