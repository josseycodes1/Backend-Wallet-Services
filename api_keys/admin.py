from django.contrib import admin
from .models import APIKey, APIKeyUsageLog

class APIKeyUsageLogInline(admin.TabularInline):
    model = APIKeyUsageLog
    extra = 0
    readonly_fields = ('id', 'endpoint', 'method', 'status_code', 'ip_address',
                      'user_agent', 'duration_ms', 'created_at')
    can_delete = False
    max_num = 10

@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'user_email', 'masked_key', 'is_active', 
                   'is_expired', 'expires_at', 'created_at')
    list_filter = ('is_active', 'created_at', 'expires_at')
    search_fields = ('name', 'user__email', 'key')
    readonly_fields = ('id', 'key', 'prefix', 'last_used_at', 'created_at', 'updated_at')
    fieldsets = (
        ('API Key Info', {
            'fields': ('user', 'name', 'key', 'prefix')
        }),
        ('Permissions & Status', {
            'fields': ('permissions', 'is_active', 'expires_at', 'last_used_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [APIKeyUsageLogInline]
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    
    def masked_key(self, obj):
        return obj.masked_key
    masked_key.short_description = 'API Key'
    
    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expired'

@admin.register(APIKeyUsageLog)
class APIKeyUsageLogAdmin(admin.ModelAdmin):
    list_display = ('api_key', 'endpoint', 'method', 'status_code', 
                   'ip_address', 'duration_ms', 'created_at')
    list_filter = ('method', 'status_code', 'created_at')
    search_fields = ('api_key__name', 'api_key__user__email', 'endpoint', 'ip_address')
    readonly_fields = ('id', 'created_at')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False