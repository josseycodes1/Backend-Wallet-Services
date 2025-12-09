from django.contrib import admin
from .models import Wallet

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('wallet_number', 'user_email', 'balance', 'currency', 'status', 'is_locked', 'created_at')
    list_filter = ('status', 'currency', 'is_locked')
    search_fields = ('wallet_number', 'user__email')
    readonly_fields = ('wallet_number', 'created_at', 'updated_at', 'last_reset_date')
    fieldsets = (
        ('Wallet Info', {
            'fields': ('user', 'wallet_number', 'balance', 'currency')
        }),
        ('Status & Limits', {
            'fields': ('status', 'is_locked', 'daily_limit', 'daily_spent', 'last_reset_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'