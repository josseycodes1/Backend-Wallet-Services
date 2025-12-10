import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
import structlog

logger = structlog.get_logger(__name__)

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('transfer', 'Transfer'),
        ('withdrawal', 'Withdrawal'),
        ('refund', 'Refund'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('reversed', 'Reversed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
   
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deposits'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_transfers'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_transfers'
    )
    
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    reference = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        blank=True,
        null=True
    )
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    
    paystack_reference = models.CharField(max_length=100, blank=True, null=True)
    paystack_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    paystack_data = models.JSONField(default=dict, blank=True)
    
    
    sender_wallet_number = models.CharField(max_length=15, blank=True, null=True)
    recipient_wallet_number = models.CharField(max_length=15, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['recipient', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
        ]
    
    def __str__(self):
        if self.transaction_type == 'transfer':
            return f"Transfer {self.id}: {self.sender_wallet_number} → {self.recipient_wallet_number} - {self.amount}"
        else:
            return f"{self.transaction_type.title()} {self.id}: {self.user.email if self.user else 'N/A'} - {self.amount}"
    
    def save(self, *args, **kwargs):
      
        if not self.reference:
            import secrets
            self.reference = f"TRX_{secrets.token_hex(12).upper()}"
        
        is_new = self._state.adding
        
        super().save(*args, **kwargs)
        
        if is_new:
            logger.info(
                "Transaction created",
                transaction_id=str(self.id),
                type=self.transaction_type,
                amount=str(self.amount),
                status=self.status
            )
        else:
            logger.info(
                "Transaction updated",
                transaction_id=str(self.id),
                type=self.transaction_type,
                amount=str(self.amount),
                status=self.status
            )
    
    @property
    def involved_user(self):
        """Get the user involved in this transaction for permission checking"""
        if self.user:
            return self.user
        elif self.sender:
            return self.sender
        elif self.recipient:
            return self.recipient
        return None
    
    @property
    def is_transfer(self):
        return self.transaction_type == 'transfer'
    
    @property
    def is_deposit(self):
        return self.transaction_type == 'deposit'
    
    def get_other_party(self, user):
        """Get the other party involved in the transaction"""
        if self.transaction_type == 'transfer':
            if user == self.sender:
                return self.recipient
            elif user == self.recipient:
                return self.sender
        return None

class TransactionLog(models.Model):
    """Log for transaction state changes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    old_status = models.CharField(max_length=20, blank=True, null=True)
    new_status = models.CharField(max_length=20)
    action = models.CharField(max_length=100)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction', 'created_at']),
        ]
    
    def __str__(self):
        return f"Log {self.id}: {self.transaction.reference} - {self.action}"