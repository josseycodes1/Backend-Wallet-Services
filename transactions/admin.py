from django.contrib import admin
from .models import Transaction, TransactionLog

class TransactionLogInline(admin.TabularInline):
    model = TransactionLog
    extra = 0
    readonly_fields = ('id', 'old_status', 'new_status', 'action', 'performed_by', 
                      'metadata', 'ip_address', 'user_agent', 'created_at')
    can_delete = False

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'get_user_email', 'transaction_type', 'amount', 
                   'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('reference', 'user__email', 'sender__email', 'recipient__email',
                    'paystack_reference', 'paystack_transaction_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Transaction Info', {
            'fields': ('reference', 'transaction_type', 'amount', 'status', 'description')
        }),
        ('Users', {
            'fields': ('user', 'sender', 'recipient')
        }),
        ('Wallet Info', {
            'fields': ('sender_wallet_number', 'recipient_wallet_number')
        }),
        ('Payment Info', {
            'fields': ('paystack_reference', 'paystack_transaction_id', 'paystack_data')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [TransactionLogInline]
    
    def get_user_email(self, obj):
        if obj.user:
            return obj.user.email
        elif obj.sender:
            return f"{obj.sender.email} → {obj.recipient.email if obj.recipient else 'N/A'}"
        return 'N/A'
    get_user_email.short_description = 'User(s)'

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'old_status', 'new_status', 'action', 
                   'performed_by', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('transaction__reference', 'performed_by__email')
    readonly_fields = ('id', 'created_at')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
