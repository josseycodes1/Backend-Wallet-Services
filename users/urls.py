from django.urls import path
from . import views

urlpatterns = [
    path('google/', views.GoogleAuthRedirectView.as_view(), name='google-auth'),
    path('google/callback/', views.GoogleAuthCallbackView.as_view(), name='google-callback'),
    path('token/', views.JWTTokenObtainView.as_view(), name='token-obtain'),
    path('profile/', views.UserProfileView.as_view(), name='user-profile'),
]