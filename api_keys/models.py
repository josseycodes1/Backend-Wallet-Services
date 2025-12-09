
import uuid
import secrets
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinLengthValidator
import structlog

logger = structlog.get_logger(__name__)

class APIKey(models.Model):
    PERMISSION_CHOICES = [
        ('read', 'Read'),
        ('deposit', 'Deposit'),
        ('transfer', 'Transfer'),
        ('all', 'All'),
    ]
    
    EXPIRY_CHOICES = [
        ('1H', '1 Hour'),
        ('1D', '1 Day'),
        ('1M', '1 Month'),
        ('1Y', '1 Year'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_keys'
    )
    name = models.CharField(max_length=100)
    key = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        editable=False
    )
    prefix = models.CharField(max_length=20, editable=False)
    permissions = models.JSONField(
        default=list,
        help_text="List of permissions: ['read', 'deposit', 'transfer']"
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['key', 'is_active']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['expires_at']),
        ]
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'
    
    def __str__(self):
        return f"{self.name} - {self.user.email}"
    
    def save(self, *args, **kwargs):
        # Generate key if not set
        if not self.key:
            self.prefix = settings.API_KEY_PREFIX
            secret_part = secrets.token_urlsafe(settings.API_KEY_LENGTH)
            self.key = f"{self.prefix}{secret_part}"
        
        super().save(*args, **kwargs)
        logger.info(
            "API Key saved",
            key_id=str(self.id),
            user_id=str(self.user.id),
            name=self.name
        )
    
    @property
    def masked_key(self):
        """Return masked version of the key for display"""
        if len(self.key) > 8:
            return f"{self.key[:8]}...{self.key[-4:]}"
        return "***"
    
    @property
    def is_expired(self):
        """Check if API key is expired"""
        return timezone.now() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if API key is valid (active and not expired)"""
        return self.is_active and not self.is_expired
    
    def has_permission(self, permission):
        """Check if API key has specific permission"""
        if 'all' in self.permissions:
            return True
        return permission in self.permissions
    
    def update_last_used(self):
        """Update last used timestamp"""
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at', 'updated_at'])
        logger.debug(
            "API Key last used updated",
            key_id=str(self.id),
            user_id=str(self.user.id)
        )
    
    @classmethod
    def get_expiry_date(cls, expiry_string):
        """Convert expiry string to datetime"""
        now = timezone.now()
        
        if expiry_string == '1H':
            return now + timezone.timedelta(hours=1)
        elif expiry_string == '1D':
            return now + timezone.timedelta(days=1)
        elif expiry_string == '1M':
            return now + timezone.timedelta(days=30)  # Approximate month
        elif expiry_string == '1Y':
            return now + timezone.timedelta(days=365)  # Approximate year
        else:
            raise ValueError(f"Invalid expiry string: {expiry_string}")
    
    def rollover(self, new_expiry_string):
        """Create a new API key with same permissions"""
        # Check if current key is expired
        if not self.is_expired:
            raise ValueError("Cannot rollover non-expired key")
        
        # Create new key
        new_key = APIKey.objects.create(
            user=self.user,
            name=f"{self.name} (Rolled over)",
            permissions=self.permissions.copy(),
            expires_at=APIKey.get_expiry_date(new_expiry_string)
        )
        
        # Deactivate old key
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])
        
        logger.info(
            "API Key rolled over",
            old_key_id=str(self.id),
            new_key_id=str(new_key.id),
            user_id=str(self.user.id)
        )
        
        return new_key

class APIKeyUsageLog(models.Model):
    """Log API key usage for auditing"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey(
        APIKey,
        on_delete=models.CASCADE,
        related_name='usage_logs'
    )
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    request_data = models.JSONField(default=dict, blank=True)
    response_data = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    duration_ms = models.IntegerField(help_text="Request duration in milliseconds")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['api_key', 'created_at']),
            models.Index(fields=['endpoint', 'created_at']),
            models.Index(fields=['status_code', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.api_key.name} - {self.endpoint} - {self.status_code}"