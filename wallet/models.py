import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
import structlog

logger = structlog.get_logger(__name__)

class Wallet(models.Model):
    CURRENCY_CHOICES = [
        ('NGN', 'Nigerian Naira'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('closed', 'Closed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    wallet_number = models.CharField(
        max_length=15,
        unique=True,
        db_index=True,
        editable=False
    )
    balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='NGN'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    daily_limit = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=1000000.00  # 1 million
    )
    daily_spent = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0.00
    )
    last_reset_date = models.DateField(auto_now_add=True)
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet_number']),
            models.Index(fields=['user', 'status']),
        ]
    
    def __str__(self):
        return f"{self.wallet_number} - {self.user.email}"
    
    def save(self, *args, **kwargs):
        if not self.wallet_number:
            self.wallet_number = self.generate_wallet_number()
        
        # Reset daily spent if it's a new day
        if self.last_reset_date != timezone.now().date():
            self.daily_spent = 0
            self.last_reset_date = timezone.now().date()
        
        super().save(*args, **kwargs)
        logger.info(
            "Wallet saved",
            wallet_id=str(self.id),
            wallet_number=self.wallet_number,
            user_id=str(self.user.id)
        )
    
    def generate_wallet_number(self):
        """Generate a unique 15-digit wallet number"""
        import random
        while True:
            # Generate 15-digit number starting with 45 (for identification)
            number = '45' + ''.join([str(random.randint(0, 9)) for _ in range(13)])
            if not Wallet.objects.filter(wallet_number=number).exists():
                return number
    
    def can_transfer(self, amount):
        """Check if wallet can perform transfer"""
        if self.is_locked:
            return False, "Wallet is locked"
        
        if self.status != 'active':
            return False, f"Wallet is {self.status}"
        
        if self.balance < amount:
            return False, "Insufficient balance"
        
        # Check daily limit
        new_daily_spent = self.daily_spent + amount
        if new_daily_spent > self.daily_limit:
            return False, "Daily transfer limit exceeded"
        
        return True, "Can transfer"
    
    def update_daily_spent(self, amount):
        """Update daily spent amount"""
        self.daily_spent += amount
        self.save(update_fields=['daily_spent', 'updated_at'])
        logger.info(
            "Daily spent updated",
            wallet_number=self.wallet_number,
            amount=str(amount),
            new_daily_spent=str(self.daily_spent)
        )