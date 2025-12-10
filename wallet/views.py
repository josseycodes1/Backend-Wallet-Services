from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import structlog

from .models import Wallet
from .serializers import (
    WalletSerializer,
    DepositRequestSerializer,
    DepositResponseSerializer,
    TransferRequestSerializer,
    TransferResponseSerializer,
    BalanceResponseSerializer,
    WalletNumberSerializer
)
from .services import PaystackService, WalletTransferService
from api_keys.permissions import HasPermission, RequireBothJWTAuthAndAPIKeyPermission

logger = structlog.get_logger(__name__)


class CreateWalletView(APIView):
    """Create a wallet for authenticated user"""
    permission_classes = [RequireBothJWTAuthAndAPIKeyPermission]
   
    
    @swagger_auto_schema(
        operation_description="Create a wallet for the authenticated user",
        responses={
            201: WalletSerializer,
            400: "Wallet already exists"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def post(self, request):
        
        if hasattr(request.user, 'wallet'):
            return Response(
                {
                    'error': 'Wallet already exists',
                    'wallet_number': request.user.wallet.wallet_number,
                    'balance': request.user.wallet.balance
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
       
        wallet = Wallet.objects.create(
            user=request.user,
            currency='NGN'
        )
        
        serializer = WalletSerializer(wallet)
        
        logger.info(
            "Wallet created via endpoint",
            user_id=str(request.user.id),
            wallet_number=wallet.wallet_number
        )
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class WalletDepositView(APIView):
    """Initialize wallet deposit with Paystack"""
    permission_classes = [RequireBothJWTAuthAndAPIKeyPermission]
    
    @swagger_auto_schema(
        operation_description="Initialize a deposit transaction with Paystack. Returns a reference you can use to check transaction status.",
        request_body=DepositRequestSerializer,
        responses={
            200: DepositResponseSerializer,
            400: "Bad Request",
            403: "Forbidden"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def post(self, request):
        serializer = DepositRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Deposit request validation failed", errors=serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        amount = serializer.validated_data['amount']
        email = serializer.validated_data.get('email', request.user.email)
        
       
        wallet, created = Wallet.objects.get_or_create(
            user=request.user,
            defaults={'currency': 'NGN'}
        )
        
        if created:
            logger.info("Wallet created for user", user_id=str(request.user.id))
        
       
        result = PaystackService.initialize_transaction(email, amount)
        
        if result['success']:
            
            from transactions.models import Transaction
            transaction = Transaction.objects.create(
                user=request.user,
                amount=amount,
                transaction_type='deposit',
                status='pending',
                reference=result['reference'],
                metadata={
                    'authorization_url': result['authorization_url'],
                    'email': email,
                    'amount': amount
                }
            )
            
            logger.info(
                "Deposit initialized",
                user_id=str(request.user.id),
                amount=amount,
                reference=result['reference']
            )
            
            
            response_data = {
                'reference': result['reference'],
                'authorization_url': result['authorization_url'],
                'amount': amount,
                'currency': 'NGN',
                'status': 'pending',
                'status_check_url': f"/wallet/deposit/{result['reference']}/status/",
                'message': f"Use this reference '{result['reference']}' to check payment status",
                'instructions': [
                    f"1. Use reference '{result['reference']}' to check status",
                    "2. Visit authorization_url to complete payment",
                    "3. Check status at GET /wallet/deposit/{reference}/status/"
                ]
            }
            
            response_serializer = DepositResponseSerializer(response_data)
            
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            logger.error(
                "Deposit initialization failed",
                user_id=str(request.user.id),
                amount=amount,
                error=result.get('message')
            )
            
            return Response(
                {'error': result.get('message', 'Payment initialization failed')},
                status=status.HTTP_400_BAD_REQUEST
            )

class WalletTransferView(APIView):
    """Transfer funds to another wallet"""
    permission_classes = [RequireBothJWTAuthAndAPIKeyPermission]
    
    @swagger_auto_schema(
        operation_description="Transfer funds to another user's wallet",
        request_body=TransferRequestSerializer,
        responses={
            200: TransferResponseSerializer,
            400: "Bad Request",
            403: "Forbidden"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def post(self, request):
        serializer = TransferRequestSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning("Transfer request validation failed", errors=serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        wallet_number = serializer.validated_data['wallet_number']
        amount = serializer.validated_data['amount']
        description = serializer.validated_data.get('description', '')
        
       
        sender_wallet = get_object_or_404(Wallet, user=request.user)
        
        
        recipient_wallet = serializer.context['recipient_wallet']
        
        
        success, message, transaction = WalletTransferService.transfer_funds(
            sender_wallet=sender_wallet,
            recipient_wallet=recipient_wallet,
            amount=amount,
            description=description
        )
        
        if success:
            response_serializer = TransferResponseSerializer({
                'status': 'success',
                'message': message,
                'transaction_id': transaction.id if transaction else None,
                'reference': str(transaction.id) if transaction else None
            })
            
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            response_serializer = TransferResponseSerializer({
                'status': 'failed',
                'message': message
            })
            
            return Response(response_serializer.data, status=status.HTTP_400_BAD_REQUEST)

class WalletBalanceView(APIView):
    """Get wallet balance"""
    permission_classes = [RequireBothJWTAuthAndAPIKeyPermission]
    
    @swagger_auto_schema(
        operation_description="Get current wallet balance",
        responses={
            200: BalanceResponseSerializer,
            404: "Wallet not found"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def get(self, request):
        try:
            wallet = Wallet.objects.get(user=request.user)
            
            response_serializer = BalanceResponseSerializer({
                'balance': wallet.balance,
                'currency': wallet.currency,
                'wallet_number': wallet.wallet_number,
                'available_balance': wallet.balance
            })
            
            logger.info(
                "Balance retrieved",
                user_id=str(request.user.id),
                wallet_number=wallet.wallet_number,
                balance=str(wallet.balance)
            )
            
            return Response(response_serializer.data, status=status.HTTP_200_OK)
            
        except Wallet.DoesNotExist:
            logger.warning("Wallet not found", user_id=str(request.user.id))
            return Response(
                {
                    'error': 'Wallet not found',
                    'message': 'You need to create a wallet first.',
                    'solution': 'Make a deposit to automatically create a wallet, or contact support.',
                    'endpoints': {
                        'create_via_deposit': 'POST /wallet/deposit/',
                        'deposit_body_example': {'amount': 1000}
                    }
                },
                status=status.HTTP_404_NOT_FOUND
            )

class DepositStatusView(APIView):
    """Check deposit status (manual verification)"""
    permission_classes = [RequireBothJWTAuthAndAPIKeyPermission]
    
    @swagger_auto_schema(
        operation_description="Check deposit status by reference",
        manual_parameters=[
            openapi.Parameter(
                'reference',
                openapi.IN_PATH,
                description="Transaction reference",
                type=openapi.TYPE_STRING
            )
        ],
        responses={
            200: openapi.Response(
                description="Deposit status",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'reference': openapi.Schema(type=openapi.TYPE_STRING),
                        'status': openapi.Schema(type=openapi.TYPE_STRING),
                        'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'currency': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            404: "Transaction not found"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def get(self, request, reference):
        
        from transactions.models import Transaction
        
        try:
            transaction = Transaction.objects.get(
                reference=reference,
                user=request.user,
                transaction_type='deposit'
            )
            
            logger.info(
                "Deposit status checked",
                reference=reference,
                user_id=str(request.user.id),
                status=transaction.status
            )
            
            return Response({
                'reference': transaction.reference,
                'status': transaction.status,
                'amount': transaction.amount,
                'currency': 'NGN' 
            }, status=status.HTTP_200_OK)
            
        except Transaction.DoesNotExist:
            logger.warning(
                "Deposit transaction not found",
                reference=reference,
                user_id=str(request.user.id)
            )
            
            return Response(
                {'error': 'Transaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def paystack_webhook(request):
    """Handle Paystack webhook notifications"""
    import json
    
    
    signature = request.headers.get('X-Paystack-Signature', '')
    payload = request.data
    
    if not PaystackService.verify_webhook_signature(payload, signature):
        logger.warning("Invalid webhook signature", signature=signature)
        return Response({'status': False}, status=status.HTTP_401_UNAUTHORIZED)
    
    
    event = payload.get('event')
    data = payload.get('data', {})
    
    logger.info(
        "Webhook received",
        event=event,
        reference=data.get('reference')
    )
    
    if event == 'charge.success':
        reference = data.get('reference')
        
       
        result = PaystackService.verify_transaction(reference)
        
        if result['success'] and result['status'] == 'success':
            
            from transactions.models import Transaction
            
            try:
                transaction = Transaction.objects.get(
                    reference=reference,
                    transaction_type='deposit',
                    status='pending'
                )
                
               
                transaction.status = 'success'
                transaction.metadata['paystack_data'] = data
                transaction.save(update_fields=['status', 'metadata', 'updated_at'])
                
                
                wallet = Wallet.objects.get(user=transaction.user)
                wallet.balance += transaction.amount
                wallet.save(update_fields=['balance', 'updated_at'])
                
                logger.info(
                    "Wallet credited via webhook",
                    reference=reference,
                    user_id=str(transaction.user.id),
                    amount=str(transaction.amount),
                    new_balance=str(wallet.balance)
                )
                
            except Transaction.DoesNotExist:
                logger.error(
                    "Transaction not found in database",
                    reference=reference
                )
            except Wallet.DoesNotExist:
                logger.error(
                    "Wallet not found for transaction",
                    reference=reference,
                    user_id=str(transaction.user.id)
                )
    
    elif event in ['charge.failed', 'transfer.failed']:
        reference = data.get('reference')
        
        
        from transactions.models import Transaction
        
        try:
            transaction = Transaction.objects.filter(
                reference=reference,
                status='pending'
            ).update(status='failed')
            
            logger.info(
                "Transaction marked as failed via webhook",
                reference=reference,
                event=event
            )
            
        except Exception as e:
            logger.error(
                "Failed to update transaction status",
                reference=reference,
                error=str(e)
            )
    
    return Response({'status': True}, status=status.HTTP_200_OK)