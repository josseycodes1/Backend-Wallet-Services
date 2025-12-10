from rest_framework import serializers
from django.conf import settings
from .models import Wallet
from users.serializers import UserSerializer
import structlog

logger = structlog.get_logger(__name__)

class WalletSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'wallet_number', 'user', 'balance', 'currency',
            'status', 'daily_limit', 'daily_spent', 'is_locked',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'wallet_number', 'user', 'balance', 'daily_spent',
            'last_reset_date', 'created_at', 'updated_at'
        ]

class DepositRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        min_value=100.00, 
        help_text="Amount to deposit in Naira (minimum: 100 NGN)"
    )
    email = serializers.EmailField(
        required=False,
        help_text="Email for payment receipt (defaults to user's email)"
    )
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value

class DepositResponseSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100, help_text="Use this reference to check transaction status")
    authorization_url = serializers.URLField(help_text="URL to complete payment")
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, coerce_to_string=True)
    currency = serializers.CharField(max_length=3, required=False, default='NGN')
    status = serializers.CharField(max_length=20, required=False, default='pending')
    status_check_url = serializers.CharField(max_length=200, required=False)
    message = serializers.CharField(max_length=200, required=False)
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass

class TransferRequestSerializer(serializers.Serializer):
    wallet_number = serializers.CharField(
        max_length=15,
        min_length=15,
        required=True,
        help_text="Recipient's 15-digit wallet number"
    )
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=1, 
        required=True
    )
    description = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True
    )
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value
    
    def validate_wallet_number(self, value):
        
        try:
            wallet = Wallet.objects.get(
                wallet_number=value,
                status='active',
                is_locked=False
            )
            self.context['recipient_wallet'] = wallet
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("Invalid wallet number or wallet is not active")
        
        
        request = self.context.get('request')
        if request and request.user:
            user_wallet = getattr(request.user, 'wallet', None)
            if user_wallet and user_wallet.wallet_number == value:
                raise serializers.ValidationError("Cannot transfer to your own wallet")
        
        return value

class TransferResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    transaction_id = serializers.UUIDField(required=False)
    reference = serializers.CharField(required=False)
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass

class BalanceResponseSerializer(serializers.Serializer):
    balance = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField()
    wallet_number = serializers.CharField()
    available_balance = serializers.DecimalField(max_digits=20, decimal_places=2)
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass

class WalletNumberSerializer(serializers.Serializer):
    wallet_number = serializers.CharField(max_length=15, min_length=15)
    
    def validate_wallet_number(self, value):
        if not Wallet.objects.filter(wallet_number=value, status='active').exists():
            raise serializers.ValidationError("Invalid wallet number")
        return value
