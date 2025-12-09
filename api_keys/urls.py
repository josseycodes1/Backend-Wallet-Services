from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.CreateAPIKeyView.as_view(), name='api-key-create'),
    path('list/', views.APIKeyListView.as_view(), name='api-key-list'),
    path('rollover/', views.RolloverAPIKeyView.as_view(), name='api-key-rollover'),
    path('revoke/', views.RevokeAPIKeyView.as_view(), name='api-key-revoke'),
    path('<uuid:pk>/update/', views.UpdateAPIKeyView.as_view(), name='api-key-update'),
]