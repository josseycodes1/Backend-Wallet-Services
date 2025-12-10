from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.CreateWalletView.as_view(), name='wallet-create'),
    path('deposit/', views.WalletDepositView.as_view(), name='wallet-deposit'),
    path('deposit/<str:reference>/status/', views.DepositStatusView.as_view(), name='deposit-status'),
    path('transfer/', views.WalletTransferView.as_view(), name='wallet-transfer'),
    path('balance/', views.WalletBalanceView.as_view(), name='wallet-balance'),
    path('paystack/webhook/', views.paystack_webhook, name='paystack-webhook'),
]