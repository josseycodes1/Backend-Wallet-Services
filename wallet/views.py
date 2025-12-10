from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import structlog
from datetime import timedelta
from decimal import Decimal
import json
from django.utils import timezone 

from .models import Wallet
from .serializers import (
    WalletSerializer,
    DepositResponseSerializer,
    TransferRequestSerializer,
    TransferResponseSerializer,
    BalanceResponseSerializer,
    WalletNumberSerializer,
    DepositRequestKoboSerializer
)
from .services import PaystackService, WalletTransferService
from api_keys.permissions import HasPermission, RequireBothJWTAuthAndAPIKeyPermission
from rest_framework import serializers, status

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
        operation_description="Initialize a deposit transaction with Paystack. Amount should be in Kobo (minimum 100 Kobo = 1 NGN). Returns a reference you can use to check transaction status.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['amount'],
            properties={
                'amount': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Amount in Kobo (minimum 100 Kobo = 1 NGN)',
                    minimum=100,
                    example=5000
                )
            }
        ),
        responses={
            201: DepositResponseSerializer,
            200: DepositResponseSerializer,
            400: "Bad Request",
            403: "Forbidden"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def post(self, request):
       
        serializer = DepositRequestKoboSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Deposit request validation failed", errors=serializer.errors)
            return Response(
                {'error': 'Invalid input', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        amount_kobo = serializer.validated_data['amount']
        amount_ngn = amount_kobo / 100  
        
      
        email = request.user.email
        if not email:
            return Response(
                {'error': 'User email is required for payment'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
           
            wallet, created = Wallet.objects.get_or_create(
                user=request.user,
                defaults={'currency': 'NGN'}
            )
            
            if created:
                logger.info("Wallet created for user", user_id=str(request.user.id))
            
            
            reference = f"DEP_{request.user.id}_{int(timezone.now().timestamp())}"
            
            
            time_threshold = timezone.now() - timedelta(minutes=10)
            
            
            from transactions.models import Transaction
            
            existing_transaction = Transaction.objects.filter(
                user=request.user,
                amount=amount_ngn,  
                status='pending',
                created_at__gte=time_threshold
            ).order_by('-created_at').first()
            
            if existing_transaction:
                logger.info(
                    "Duplicate deposit request detected, returning existing transaction",
                    user_id=str(request.user.id),
                    amount=amount_ngn,
                    reference=existing_transaction.reference
                )
                
                response_data = {
                    'reference': existing_transaction.reference,
                    'authorization_url': existing_transaction.metadata.get('authorization_url', ''),
                    'amount': amount_kobo,  
                    'currency': 'NGN',
                    'status': 'pending',
                    'status_check_url': f"/wallet/deposit/{existing_transaction.reference}/status/",
                    'message': f"Use this reference '{existing_transaction.reference}' to check payment status",
                    'instructions': [
                        f"1. Use reference '{existing_transaction.reference}' to check status",
                        "2. Visit authorization_url to complete payment",
                        "3. Check status at GET /wallet/deposit/{reference}/status/"
                    ]
                }
                
                response_serializer = DepositResponseSerializer(response_data)
                return Response(response_serializer.data, status=status.HTTP_200_OK)
            
           
            result = PaystackService.initialize_transaction(email, amount_kobo)  
            
            if not result.get('success'):
                logger.error(
                    "Paystack deposit initialization failed",
                    user_id=str(request.user.id),
                    amount_kobo=amount_kobo,
                    error=result.get('message')
                )
                
                return Response(
                    {
                        'error': 'Payment initialization failed',
                        'detail': result.get('message', 'Paystack service error')
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )
            
            
            transaction = Transaction.objects.create(
                user=request.user,
                amount=amount_ngn,  
                transaction_type='deposit',
                status='pending',
                reference=reference,
                metadata={
                    'authorization_url': result.get('authorization_url'),
                    'email': email,
                    'amount_kobo': amount_kobo, 
                    'amount_ngn': amount_ngn,
                    'paystack_reference': result.get('reference'),
                    'paystack_response': result
                }
            )
            
            logger.info(
                "Deposit initialized successfully",
                user_id=str(request.user.id),
                amount_kobo=amount_kobo,
                amount_ngn=amount_ngn,
                reference=reference
            )
            
            
            response_data = {
                'reference': reference,
                'authorization_url': result.get('authorization_url'),
                'amount': amount_kobo,  
                'currency': 'NGN',
                'status': 'pending',
                'status_check_url': f"/wallet/deposit/{reference}/status/",
                'message': f"Use this reference '{reference}' to check payment status",
                'instructions': [
                    f"1. Use reference '{reference}' to check status",
                    "2. Visit authorization_url to complete payment",
                    "3. Check status at GET /wallet/deposit/{reference}/status/"
                ]
            }
            
            response_serializer = DepositResponseSerializer(response_data)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(
                "Unexpected error in deposit initialization",
                user_id=str(request.user.id),
                error=str(e)
            )
            
            return Response(
                {
                    'error': 'Internal server error',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class WalletTransferView(APIView):
    """Transfer funds to another wallet - amount in Kobo"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Transfer funds to another user's wallet. Amount should be in Kobo (minimum 100 Kobo = 1 NGN).",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['wallet_number', 'amount'],
            properties={
                'wallet_number': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Recipient's 15-digit wallet number",
                    minLength=15,
                    maxLength=15,
                    example="453381966070708"
                ),
                'amount': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Amount in Kobo (minimum 100 Kobo = 1 NGN)',
                    minimum=100,
                    example=5000
                ),
                'description': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Transfer description (optional)",
                    maxLength=255
                )
            }
        ),
        responses={
            200: TransferResponseSerializer,
            400: "Bad Request",
            403: "Forbidden"
        },
        security=[{'Bearer': []}]
    )
    def post(self, request):
      
        class TransferKoboRequestSerializer(serializers.Serializer):
            wallet_number = serializers.CharField(
                max_length=15,
                min_length=15,
                required=True,
                help_text="Recipient's 15-digit wallet number"
            )
            amount = serializers.IntegerField(
                min_value=100,
                required=True,
                help_text="Amount in Kobo (minimum 100 Kobo = 1 NGN)"
            )
            description = serializers.CharField(
                max_length=255,
                required=False,
                allow_blank=True
            )
            
            def validate_amount(self, value):
                if value < 100:
                    raise serializers.ValidationError("Amount must be at least 100 Kobo (1 NGN)")
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
        
        serializer = TransferKoboRequestSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.warning("Transfer request validation failed", errors=serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        wallet_number = serializer.validated_data['wallet_number']
        amount_kobo = serializer.validated_data['amount']
        description = serializer.validated_data.get('description', '')
        
        
        amount_ngn = amount_kobo / 100
        
      
        sender_wallet = get_object_or_404(Wallet, user=request.user)
        
        
        recipient_wallet = serializer.context.get('recipient_wallet')
        if not recipient_wallet:
            return Response(
                {
                    'status': 'failed',
                    'message': f'Wallet with number {wallet_number} not found'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
       
        if sender_wallet.wallet_number == recipient_wallet.wallet_number:
            return Response(
                {
                    'status': 'failed',
                    'message': 'Cannot transfer to your own wallet'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check sender has sufficient balance (in NGN)
        if sender_wallet.balance < Decimal(str(amount_ngn)):
            return Response(
                {
                    'status': 'failed',
                    'message': f'Insufficient balance. Available: {sender_wallet.balance} NGN ({int(sender_wallet.balance * 100)} Kobo)'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
           
            from django.db import transaction as db_transaction
            
            with db_transaction.atomic():
               
                sender_wallet.balance -= Decimal(str(amount_ngn))
                sender_wallet.save(update_fields=['balance', 'updated_at'])
                
                
                recipient_wallet.balance += Decimal(str(amount_ngn))
                recipient_wallet.save(update_fields=['balance', 'updated_at'])
                
                
                from transactions.models import Transaction
                transaction = Transaction.objects.create(
                    sender=request.user,
                    recipient=recipient_wallet.user,
                    amount=amount_ngn,
                    transaction_type='transfer',
                    status='success',
                    sender_wallet_number=sender_wallet.wallet_number,
                    recipient_wallet_number=recipient_wallet.wallet_number,
                    description=description,
                    metadata={
                        'transfer_type': 'wallet_to_wallet',
                        'sender_email': request.user.email,
                        'recipient_email': recipient_wallet.user.email,
                        'amount_kobo': amount_kobo,
                        'amount_ngn': str(amount_ngn)
                    }
                )
                
                logger.info(
                    "Transfer completed successfully",
                    transaction_id=str(transaction.id),
                    sender=sender_wallet.wallet_number,
                    recipient=recipient_wallet.wallet_number,
                    amount_kobo=amount_kobo,
                    amount_ngn=amount_ngn
                )
                
                response_serializer = TransferResponseSerializer({
                    'status': 'success',
                    'message': f'Transfer of {amount_kobo} Kobo ({amount_ngn} NGN) to wallet {wallet_number} completed successfully',
                    'transaction_id': transaction.id,
                    'reference': transaction.reference
                })
                
                return Response(response_serializer.data, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(
                "Transfer failed",
                sender=sender_wallet.wallet_number,
                recipient=recipient_wallet.wallet_number,
                amount_kobo=amount_kobo,
                error=str(e)
            )
            
            response_serializer = TransferResponseSerializer({
                'status': 'failed',
                'message': f'Transfer failed: {str(e)}'
            })
            
            return Response(response_serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    """Check deposit status with Paystack verification"""
    permission_classes = [RequireBothJWTAuthAndAPIKeyPermission]
    
    @swagger_auto_schema(
        operation_description="Check deposit status by reference with optional Paystack verification",
        manual_parameters=[
            openapi.Parameter(
                'reference',
                openapi.IN_PATH,
                description="Transaction reference",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'refresh',
                openapi.IN_QUERY,
                description="Force refresh from Paystack (true/false)",
                type=openapi.TYPE_BOOLEAN,
                required=False,
                default=False
            )
        ],
        responses={
            200: openapi.Response(
                description="Deposit status",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'reference': openapi.Schema(type=openapi.TYPE_STRING),
                        'status': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            enum=['pending', 'success', 'failed', 'abandoned']
                        ),
                        'amount_kobo': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'amount_ngn': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'currency': openapi.Schema(type=openapi.TYPE_STRING),
                        'paid_at': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='date-time',
                            nullable=True
                        ),
                        'authorization_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='url',
                            nullable=True
                        ),
                        'requires_action': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                    }
                )
            ),
            404: "Transaction not found",
            500: "Internal server error"
        },
        security=[{'Bearer': []}, {'APIKey': []}]
    )
    def get(self, request, reference):
        """Check deposit status with optional Paystack verification"""
        
        refresh = request.GET.get('refresh', 'false').lower() == 'true'
        
        try:
           
            from transactions.models import Transaction
            
            
            transaction = Transaction.objects.get(
                reference=reference,
                user=request.user,
                transaction_type='deposit'
            )
            
            
            should_verify = (
                refresh or 
                transaction.status == 'pending' or
                (transaction.created_at and 
                 timezone.now() - transaction.created_at < timedelta(hours=24))
            )
            
            paystack_verification = None
            
            if should_verify:
               
                paystack_reference = transaction.metadata.get('paystack_reference')
                if not paystack_reference and 'reference' in transaction.metadata:
                    paystack_reference = transaction.metadata.get('reference')
                
                
                if paystack_reference:
                    paystack_verification = PaystackService.verify_transaction(paystack_reference)
                    
                    if paystack_verification.get('success'):
                        paystack_status = paystack_verification.get('status')
                        
                        
                        status_mapping = {
                            'success': 'success',
                            'failed': 'failed',
                            'abandoned': 'abandoned',
                            'pending': 'pending'
                        }
                        
                        new_status = status_mapping.get(paystack_status, 'pending')
                        
                        
                        if new_status != transaction.status:
                            transaction.status = new_status
                            
                           
                            if 'data' in paystack_verification:
                                transaction.metadata['paystack_verification'] = paystack_verification['data']
                                transaction.metadata['last_verified_at'] = timezone.now().isoformat()
                            
                           
                            if new_status == 'success':
                                paid_at_str = paystack_verification.get('data', {}).get('paid_at')
                                if paid_at_str:
                                    try:
                                       
                                        from django.utils.dateparse import parse_datetime
                                        paid_at = parse_datetime(paid_at_str)
                                        if paid_at:
                                            transaction.paid_at = paid_at
                                    except (ValueError, TypeError):
                                        transaction.paid_at = timezone.now()
                                else:
                                    transaction.paid_at = timezone.now()
                            
                            transaction.save()
                            
                            logger.info(
                                "Transaction status updated from Paystack",
                                reference=reference,
                                old_status=transaction.status,
                                new_status=new_status,
                                paystack_status=paystack_status
                            )
                    else:
                        logger.warning(
                            "Paystack verification failed",
                            reference=reference,
                            paystack_error=paystack_verification.get('message')
                        )
            
            
            authorization_url = transaction.metadata.get('authorization_url', '')
            
            
            requires_action = (
                transaction.status == 'pending' and 
                authorization_url and
                (not transaction.paid_at or 
                 timezone.now() - transaction.created_at < timedelta(minutes=30))
            )
            
            
            amount_kobo = transaction.metadata.get('amount_kobo')
            if not amount_kobo and transaction.amount:
                amount_kobo = int(transaction.amount * 100)
            
            response_data = {
                'reference': transaction.reference,
                'status': transaction.status,
                'amount_kobo': amount_kobo,
                'amount_ngn': transaction.amount if transaction.amount else amount_kobo / 100,
                'currency': 'NGN',
                'paid_at': transaction.metadata.get('paid_at') if transaction.metadata.get('paid_at') else None,
                'authorization_url': authorization_url if requires_action else None,
                'requires_action': requires_action,
                'verified_with_paystack': paystack_verification is not None and paystack_verification.get('success'),
                'last_updated': transaction.updated_at.isoformat() if transaction.updated_at else None
            }
            
            logger.info(
                "Deposit status checked",
                reference=reference,
                user_id=str(request.user.id),
                status=transaction.status,
                verified=paystack_verification is not None
            )
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Transaction.DoesNotExist:
            logger.warning(
                "Deposit transaction not found",
                reference=reference,
                user_id=str(request.user.id)
            )
            
            return Response(
                {
                    'error': 'Transaction not found',
                    'message': 'No deposit transaction found with this reference',
                    'reference': reference,
                    'user_id': str(request.user.id)
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(
                "Error checking deposit status",
                reference=reference,
                user_id=str(request.user.id),
                error=str(e)
            )
            
            return Response(
                {
                    'error': 'Internal server error',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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