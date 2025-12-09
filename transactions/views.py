from django.db import models  # Add this import
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status, generics, permissions, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import structlog

from .models import Transaction
from .serializers import (
    TransactionSerializer,
    TransactionHistorySerializer,
    TransactionFilterSerializer
)
from api_keys.permissions import HasPermission

logger = structlog.get_logger(__name__)

class TransactionHistoryView(APIView):
    """Get transaction history for authenticated user"""
    permission_classes = [permissions.IsAuthenticated | HasPermission('read')]
    
    @swagger_auto_schema(
        operation_description="Get transaction history with filtering options",
        query_serializer=TransactionFilterSerializer,
        responses={
            200: TransactionHistorySerializer(many=True),
            400: "Bad Request"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def get(self, request):
        filter_serializer = TransactionFilterSerializer(data=request.query_params)
        if not filter_serializer.is_valid():
            return Response(
                filter_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        filters_data = filter_serializer.validated_data
        
        # Base queryset - transactions where user is involved
        queryset = Transaction.objects.filter(
            models.Q(user=request.user) |
            models.Q(sender=request.user) |
            models.Q(recipient=request.user)
        ).distinct()
        
        # Apply filters
        if filters_data['transaction_type'] != 'all':
            queryset = queryset.filter(transaction_type=filters_data['transaction_type'])
        
        if filters_data['status'] != 'all':
            queryset = queryset.filter(status=filters_data['status'])
        
        if filters_data.get('start_date'):
            queryset = queryset.filter(created_at__date__gte=filters_data['start_date'])
        
        if filters_data.get('end_date'):
            queryset = queryset.filter(created_at__date__lte=filters_data['end_date'])
        
        # Apply pagination
        limit = filters_data['limit']
        offset = filters_data['offset']
        
        total_count = queryset.count()
        transactions = queryset.order_by('-created_at')[offset:offset + limit]
        
        # Prepare response data
        response_data = []
        for transaction in transactions:
            transaction_data = {
                'type': transaction.transaction_type,
                'amount': transaction.amount,
                'status': transaction.status,
                'reference': transaction.reference,
                'description': transaction.description,
                'created_at': transaction.created_at,
                'counterparty': None
            }
            
            # Add counterparty info for transfers
            if transaction.transaction_type == 'transfer':
                if request.user == transaction.sender:
                    transaction_data['counterparty'] = {
                        'type': 'recipient',
                        'email': transaction.recipient.email if transaction.recipient else None,
                        'wallet_number': transaction.recipient_wallet_number
                    }
                elif request.user == transaction.recipient:
                    transaction_data['counterparty'] = {
                        'type': 'sender',
                        'email': transaction.sender.email if transaction.sender else None,
                        'wallet_number': transaction.sender_wallet_number
                    }
            
            response_data.append(transaction_data)
        
        logger.info(
            "Transaction history retrieved",
            user_id=str(request.user.id),
            total_count=total_count,
            returned_count=len(response_data)
        )
        
        return Response(response_data, status=status.HTTP_200_OK)

class TransactionDetailView(generics.RetrieveAPIView):
    """Get details of a specific transaction"""
    permission_classes = [permissions.IsAuthenticated | HasPermission('read')]
    serializer_class = TransactionSerializer
    lookup_field = 'reference'
    lookup_url_kwarg = 'reference'
    
    def get_queryset(self):
        # User can only see transactions they're involved in
        return Transaction.objects.filter(
            models.Q(user=self.request.user) |
            models.Q(sender=self.request.user) |
            models.Q(recipient=self.request.user)
        ).distinct()
    
    @swagger_auto_schema(
        operation_description="Get details of a specific transaction by reference",
        manual_parameters=[
            openapi.Parameter(
                'reference',
                openapi.IN_PATH,
                description="Transaction reference",
                type=openapi.TYPE_STRING
            )
        ],
        responses={
            200: TransactionSerializer,
            404: "Transaction not found"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class TransactionStatsView(APIView):
    """Get transaction statistics"""
    permission_classes = [permissions.IsAuthenticated | HasPermission('read')]
    
    @swagger_auto_schema(
        operation_description="Get transaction statistics",
        responses={
            200: openapi.Response(
                description="Transaction statistics",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'total_transactions': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'total_deposits': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'total_transfers': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'total_deposit_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'total_transfer_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'successful_transactions': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'failed_transactions': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'pending_transactions': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'today_transactions': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'this_month_transactions': openapi.Schema(type=openapi.TYPE_INTEGER),
                    }
                )
            )
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def get(self, request):
        # Get base queryset
        queryset = Transaction.objects.filter(
            models.Q(user=request.user) |
            models.Q(sender=request.user) |
            models.Q(recipient=request.user)
        ).distinct()
        
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        stats = {
            'total_transactions': queryset.count(),
            'total_deposits': queryset.filter(transaction_type='deposit').count(),
            'total_transfers': queryset.filter(transaction_type='transfer').count(),
            'total_deposit_amount': float(queryset.filter(
                transaction_type='deposit',
                status='success'
            ).aggregate(models.Sum('amount'))['amount__sum'] or 0),
            'total_transfer_amount': float(queryset.filter(
                transaction_type='transfer',
                status='success'
            ).aggregate(models.Sum('amount'))['amount__sum'] or 0),
            'successful_transactions': queryset.filter(status='success').count(),
            'failed_transactions': queryset.filter(status='failed').count(),
            'pending_transactions': queryset.filter(status='pending').count(),
            'today_transactions': queryset.filter(created_at__date=today).count(),
            'this_month_transactions': queryset.filter(
                created_at__date__gte=month_start
            ).count(),
        }
        
        logger.info(
            "Transaction stats retrieved",
            user_id=str(request.user.id),
            stats=stats
        )
        
        return Response(stats, status=status.HTTP_200_OK)