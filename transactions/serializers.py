from rest_framework import serializers
from django.conf import settings
from .models import Transaction, TransactionLog
from users.serializers import UserSerializer
import structlog

logger = structlog.get_logger(__name__)

class TransactionLogSerializer(serializers.ModelSerializer):
    performed_by = UserSerializer(read_only=True)
    
    class Meta:
        model = TransactionLog
        fields = [
            'id', 'old_status', 'new_status', 'action',
            'performed_by', 'metadata', 'ip_address',
            'user_agent', 'created_at'
        ]
        read_only_fields = fields

class TransactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    sender = UserSerializer(read_only=True)
    recipient = UserSerializer(read_only=True)
    logs = TransactionLogSerializer(many=True, read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'sender', 'recipient', 'amount',
            'transaction_type', 'status', 'reference',
            'description', 'metadata', 'paystack_reference',
            'paystack_transaction_id', 'sender_wallet_number',
            'recipient_wallet_number', 'created_at', 'updated_at',
            'logs'
        ]
        read_only_fields = fields
    
    def to_representation(self, instance):
        """Custom representation to show relevant user info"""
        data = super().to_representation(instance)
        request = self.context.get('request')
        
        if request and request.user:
            
            if instance.transaction_type == 'transfer':
                if request.user == instance.sender:
                    data['counterparty'] = {
                        'type': 'recipient',
                        'user': UserSerializer(instance.recipient).data
                    }
                elif request.user == instance.recipient:
                    data['counterparty'] = {
                        'type': 'sender',
                        'user': UserSerializer(instance.sender).data
                    }
        
        return data

class TransactionHistorySerializer(serializers.Serializer):
    """Serializer for transaction history response"""
    type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    status = serializers.CharField()
    reference = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    counterparty = serializers.DictField(allow_null=True)
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass

class TransactionFilterSerializer(serializers.Serializer):
    """Serializer for transaction filtering"""
    transaction_type = serializers.ChoiceField(
        choices=['deposit', 'transfer', 'withdrawal', 'refund', 'all'],
        default='all',
        required=False
    )
    status = serializers.ChoiceField(
        choices=['pending', 'success', 'failed', 'cancelled', 'reversed', 'all'],
        default='all',
        required=False
    )
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20, required=False)
    offset = serializers.IntegerField(min_value=0, default=0, required=False)
    
    def validate(self, attrs):
        if attrs.get('start_date') and attrs.get('end_date'):
            if attrs['start_date'] > attrs['end_date']:
                raise serializers.ValidationError("start_date cannot be after end_date")
        return attrs
    
class TransactionStatsSerializer(serializers.Serializer):
    """Serializer for transaction statistics response"""
    total_transactions = serializers.IntegerField()
    total_deposits = serializers.IntegerField()
    total_transfers = serializers.IntegerField()
    total_deposit_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_transfer_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    successful_transactions = serializers.IntegerField()
    failed_transactions = serializers.IntegerField()
    pending_transactions = serializers.IntegerField()
    today_transactions = serializers.IntegerField()
    this_month_transactions = serializers.IntegerField()
    
    def create(self, validated_data):
        pass
    
    def update(self, instance, validated_data):
        pass