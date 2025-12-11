from django.urls import path
from . import views

urlpatterns = [
    path('google/', views.GoogleAuthRedirectView.as_view(), name='google-auth'),
    path('google/callback/', views.GoogleAuthCallbackView.as_view(), name='google-callback'),
]