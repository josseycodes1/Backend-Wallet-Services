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
from django.db import models 

from .models import Wallet, Transaction 

from .serializers import (
    WalletSerializer,
    DepositResponseSerializer,
    TransferRequestSerializer,
    TransferResponseSerializer,
    BalanceResponseSerializer,
    WalletNumberSerializer,
    DepositRequestKoboSerializer,
    TransactionHistoryItemSerializer,  
    TransactionFilterSerializer  
)
from drf_yasg.utils import swagger_auto_schema
from .services import PaystackService, WalletTransferService
from api_keys.permissions import HasPermission, RequireBothJWTAuthAndAPIKeyPermission
from rest_framework import serializers

logger = structlog.get_logger(__name__)

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
           
            wallet = Wallet.objects.get(user=request.user)
            
            reference = f"DEP_{request.user.id}_{int(timezone.now().timestamp())}"
            
            time_threshold = timezone.now() - timedelta(minutes=10)
            
           
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
                    'paystack_response': result,
                    'wallet_id': str(wallet.id),
                    'wallet_number': wallet.wallet_number
                }
            )
            
            logger.info(
                "Deposit initialized successfully",
                user_id=str(request.user.id),
                wallet_id=str(wallet.id),
                wallet_number=wallet.wallet_number,
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
            
        except Wallet.DoesNotExist:
            logger.error(
                "Wallet not found for deposit",
                user_id=str(request.user.id),
                email=email
            )
            
            return Response(
                {
                    'error': 'Wallet not found',
                    'message': 'You need to authenticate first to create a wallet.',
                    'solution': 'Authenticate via Google OAuth to automatically create a wallet.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
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
        
        try:
           
            sender_wallet = Wallet.objects.get(user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {
                    'status': 'failed',
                    'message': 'Sender wallet not found. Please authenticate via Google OAuth first to create a wallet.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
    
        if sender_wallet.status != 'active' or sender_wallet.is_locked:
            return Response(
                {
                    'status': 'failed',
                    'message': 'Your wallet is not active or has been locked. Please contact support.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
       
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
        
      
        if sender_wallet.balance < Decimal(str(amount_ngn)):
            return Response(
                {
                    'status': 'failed',
                    'message': f'Insufficient balance. Available: {sender_wallet.balance} NGN ({int(sender_wallet.balance * 100)} Kobo)'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        
        if sender_wallet.daily_limit and (sender_wallet.daily_spent + Decimal(str(amount_ngn))) > sender_wallet.daily_limit:
            return Response(
                {
                    'status': 'failed',
                    'message': f'Daily transfer limit exceeded. Daily limit: {sender_wallet.daily_limit} NGN, Already spent: {sender_wallet.daily_spent} NGN'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
         
            from django.db import transaction as db_transaction
            
            with db_transaction.atomic():
               
                sender_wallet.balance -= Decimal(str(amount_ngn))
                
             
                sender_wallet.daily_spent += Decimal(str(amount_ngn))
                sender_wallet.save(update_fields=['balance', 'daily_spent', 'updated_at'])
                
               
                recipient_wallet.balance += Decimal(str(amount_ngn))
                recipient_wallet.save(update_fields=['balance', 'updated_at'])
                
                
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
                        'sender_wallet_id': str(sender_wallet.id),
                        'recipient_wallet_id': str(recipient_wallet.id),
                        'amount_kobo': amount_kobo,
                        'amount_ngn': str(amount_ngn)
                    }
                )
                
                logger.info(
                    "Transfer completed successfully",
                    transaction_id=str(transaction.id),
                    sender_wallet_id=str(sender_wallet.id),
                    sender_wallet_number=sender_wallet.wallet_number,
                    recipient_wallet_id=str(recipient_wallet.id),
                    recipient_wallet_number=recipient_wallet.wallet_number,
                    amount_kobo=amount_kobo,
                    amount_ngn=amount_ngn
                )
                
                response_serializer = TransferResponseSerializer({
                    'status': 'success',
                    'message': f'Transfer of {amount_kobo} Kobo ({amount_ngn} NGN) to wallet {wallet_number} completed successfully',
                    'transaction_id': transaction.id,
                    'reference': transaction.reference,
                    'amount_kobo': amount_kobo,
                    'amount_ngn': amount_ngn
                })
                
                return Response(response_serializer.data, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(
                "Transfer failed",
                sender_wallet_id=str(sender_wallet.id) if sender_wallet else None,
                sender_wallet_number=sender_wallet.wallet_number if sender_wallet else None,
                recipient_wallet_number=wallet_number,
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
                'available_balance': wallet.balance,
                'wallet_id': str(wallet.id),
                'status': wallet.status,
                'daily_limit': wallet.daily_limit,
                'daily_spent': wallet.daily_spent,
                'is_locked': wallet.is_locked
            })
            
            logger.info(
                "Balance retrieved",
                user_id=str(request.user.id),
                wallet_id=str(wallet.id),
                wallet_number=wallet.wallet_number,
                balance=str(wallet.balance)
            )
            
            return Response(response_serializer.data, status=status.HTTP_200_OK)
            
        except Wallet.DoesNotExist:
            logger.warning("Wallet not found", user_id=str(request.user.id))
            return Response(
                {
                    'error': 'Wallet not found',
                    'message': 'You need to authenticate first to create a wallet.',
                    'solution': 'Authenticate via Google OAuth to automatically create a wallet.'
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
                'paid_at': transaction.paid_at.isoformat() if transaction.paid_at else None,
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


@swagger_auto_schema(
    method='post',
    operation_description="""Handle Paystack webhooks for transaction status updates.
    
    Always returns 200 OK with {"status": true} to prevent Paystack from retrying webhook delivery.
    Signature verification is performed but errors are logged, not returned.
    
    Note: This endpoint does not require authentication as it's called by Paystack servers.
    """,
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['event', 'data'],
        properties={
            'event': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Webhook event type',
                enum=['charge.success', 'charge.failed', 'transfer.success', 'transfer.failed']
            ),
            'data': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='Event data payload',
                properties={
                    'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'reference': openapi.Schema(type=openapi.TYPE_STRING),
                    'amount': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'currency': openapi.Schema(type=openapi.TYPE_STRING),
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'paid_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
                    'gateway_response': openapi.Schema(type=openapi.TYPE_STRING),
                    'customer': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'email': openapi.Schema(type=openapi.TYPE_STRING),
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER)
                        }
                    )
                }
            )
        }
    ),
    manual_parameters=[
        openapi.Parameter(
            'X-Paystack-Signature',
            openapi.IN_HEADER,
            description="Paystack webhook signature for verification (optional for testing)",
            type=openapi.TYPE_STRING,
            required=False
        )
    ],
    security=[],  # No authentication required
    responses={
        200: openapi.Response(
            description="Webhook processed successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_BOOLEAN, default=True)
                }
            ),
            examples={
                "application/json": {
                    "status": True
                }
            }
        )
    }
)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def paystack_webhook(request):
    """Handle Paystack webhook notifications - Always returns 200 OK"""
    import json
    
    # Initialize response - ALWAYS success for Paystack
    response_data = {'status': True}
    
    # Get the raw request body
    try:
        payload = request.body.decode('utf-8')
    except Exception as e:
        logger.error("Failed to decode request body", error=str(e))
        return Response(response_data, status=status.HTTP_200_OK)
    
    signature = request.headers.get('X-Paystack-Signature', '')
    
    # Log the webhook receipt
    logger.info("Paystack webhook endpoint called")
    
    # Verify signature if present
    if signature:
        if PaystackService.verify_webhook_signature(payload, signature):
            logger.info("Signature verification successful")
        else:
            logger.warning("Invalid Paystack signature", signature=signature[:20] + "...")
    else:
        logger.warning("Missing Paystack signature in webhook")
    
    # Parse JSON payload
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in webhook payload", error=str(e))
        # Still return 200 to prevent Paystack retries
        return Response(response_data, status=status.HTTP_200_OK)
    
    event = data.get('event')
    payload_data = data.get('data', {})
    
    logger.info(
        "Webhook processing",
        event=event,
        reference=payload_data.get('reference'),
        amount=payload_data.get('amount')
    )
    
    try:
        if event == 'charge.success':
            reference = payload_data.get('reference')
            
            if not reference:
                logger.error("Missing reference in charge.success webhook")
                return Response(response_data, status=status.HTTP_200_OK)
            
            # Additional verification from Paystack
            result = PaystackService.verify_transaction(reference)
            
            if not result.get('success'):
                logger.error("Paystack verification failed", reference=reference, error=result.get('message'))
                # Still process if we have the data
                logger.warning("Proceeding with webhook data despite verification failure")
            
            # Try to find and process the transaction
            try:
                # First try to find by paystack_reference in metadata
                transaction = Transaction.objects.filter(
                    metadata__paystack_reference=reference,
                    transaction_type='deposit',
                    status='pending'
                ).first()
                
                # If not found, try by our reference
                if not transaction:
                    transaction = Transaction.objects.filter(
                        reference=reference,
                        transaction_type='deposit',
                        status='pending'
                    ).first()
                
                if transaction:
                    logger.info(
                        "Processing successful charge",
                        reference=reference,
                        transaction_id=str(transaction.id),
                        user_id=str(transaction.user.id)
                    )
                    
                    # Update transaction status
                    transaction.status = 'success'
                    transaction.metadata['paystack_webhook_data'] = data
                    transaction.metadata['webhook_processed_at'] = timezone.now().isoformat()
                    
                    if result and 'data' in result:
                        transaction.metadata['paystack_verification'] = result['data']
                    
                    # Add paid_at if available
                    paid_at_str = payload_data.get('paid_at')
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
                    
                    transaction.save(update_fields=['status', 'metadata', 'paid_at', 'updated_at'])
                    
                    # Credit the user's wallet
                    try:
                        wallet = Wallet.objects.get(user=transaction.user)
                        old_balance = wallet.balance
                        wallet.balance += transaction.amount
                        wallet.save(update_fields=['balance', 'updated_at'])
                        
                        logger.info(
                            "Wallet credited via webhook",
                            reference=reference,
                            user_id=str(transaction.user.id),
                            user_email=transaction.user.email,
                            amount=str(transaction.amount),
                            old_balance=str(old_balance),
                            new_balance=str(wallet.balance)
                        )
                        
                        # Add to response data for debugging
                        response_data['wallet_credited'] = True
                        response_data['new_balance'] = str(wallet.balance)
                        
                    except Wallet.DoesNotExist:
                        logger.error(
                            "Wallet not found for transaction",
                            reference=reference,
                            user_id=str(transaction.user.id)
                        )
                        response_data['wallet_error'] = 'Wallet not found'
                else:
                    logger.warning(
                        "Transaction not found for successful charge",
                        reference=reference
                    )
                    response_data['transaction_not_found'] = True
                    
            except Exception as e:
                logger.error("Error processing successful charge", reference=reference, error=str(e), exc_info=True)
                response_data['processing_error'] = str(e)
        
        elif event == 'charge.failed':
            reference = payload_data.get('reference')
            
            if reference:
                try:
                    # Find and update the transaction
                    transaction = Transaction.objects.filter(
                        models.Q(metadata__paystack_reference=reference) | 
                        models.Q(reference=reference),
                        transaction_type='deposit',
                        status='pending'
                    ).first()
                    
                    if transaction:
                        transaction.status = 'failed'
                        transaction.metadata['paystack_webhook_data'] = data
                        transaction.metadata['webhook_processed_at'] = timezone.now().isoformat()
                        transaction.metadata['failure_reason'] = payload_data.get('gateway_response', 'Payment failed')
                        transaction.save(update_fields=['status', 'metadata', 'updated_at'])
                        
                        logger.info(
                            "Transaction marked as failed via webhook",
                            reference=reference,
                            event=event,
                            failure_reason=payload_data.get('gateway_response')
                        )
                        response_data['transaction_marked_failed'] = True
                    
                except Exception as e:
                    logger.error("Error processing failed charge", reference=reference, error=str(e))
                    response_data['failed_charge_error'] = str(e)
        
        elif event == 'transfer.success':
            reference = payload_data.get('reference')
            logger.info("Transfer success webhook received", reference=reference)
            response_data['transfer_success'] = True
        
        elif event == 'transfer.failed':
            reference = payload_data.get('reference')
            logger.info("Transfer failed webhook received", reference=reference)
            response_data['transfer_failed'] = True
        
        else:
            logger.info(f"Unhandled webhook event received: {event}")
            response_data['unhandled_event'] = event
        
    except Exception as e:
        logger.error("Unexpected error in webhook handler", error=str(e), exc_info=True)
        response_data['unexpected_error'] = str(e)
    
    # ALWAYS return 200 OK to Paystack to acknowledge receipt
    # This prevents Paystack from retrying the webhook
    logger.info("Webhook processing complete", response=response_data)
    return Response(response_data, status=status.HTTP_200_OK)

class WalletTransactionsView(APIView):
    """Get transaction history for authenticated user"""
    permission_classes = [RequireBothJWTAuthAndAPIKeyPermission]
    
    @swagger_auto_schema(
        operation_description="Get transaction history for the authenticated user's wallet with filtering options",
        query_serializer=TransactionFilterSerializer,
        responses={
            200: openapi.Response(
                description="Transaction history retrieved successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'transactions': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'type': openapi.Schema(type=openapi.TYPE_STRING),
                                    'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                                    'created_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
                                    'direction': openapi.Schema(type=openapi.TYPE_STRING),
                                    'counterparty_wallet': openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                                    'reference': openapi.Schema(type=openapi.TYPE_STRING),
                                    'description': openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                                    'transaction_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid')
                                }
                            )
                        ),
                        'pagination': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'total': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'limit': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'offset': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'has_more': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                            }
                        )
                    }
                )
            ),
            404: "Wallet not found",
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
        
        try:
            
            wallet = Wallet.objects.get(user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {
                    'error': 'Wallet not found',
                    'message': 'You need to authenticate first to create a wallet.',
                    'solution': 'Authenticate via Google OAuth to automatically create a wallet.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        
        queryset = Transaction.objects.filter(
            models.Q(user=request.user) |  
            models.Q(sender=request.user) |  
            models.Q(recipient=request.user)  
        ).distinct()
        
       
        if filters_data['transaction_type'] != 'all':
            queryset = queryset.filter(transaction_type=filters_data['transaction_type'])
        
        if filters_data['status'] != 'all':
            queryset = queryset.filter(status=filters_data['status'])
        
        if filters_data.get('start_date'):
            queryset = queryset.filter(created_at__date__gte=filters_data['start_date'])
        
        if filters_data.get('end_date'):
            queryset = queryset.filter(created_at__date__lte=filters_data['end_date'])
        
       
        limit = filters_data['limit']
        offset = filters_data['offset']
        
        total_count = queryset.count()
        has_more = (offset + limit) < total_count
        
        transactions = queryset.order_by('-created_at')[offset:offset + limit]
        
       
        transactions_list = []
        for transaction in transactions:
           
            transaction_type = transaction.transaction_type
            direction = ""
            counterparty_wallet = None
            
            if transaction_type == 'deposit':
                direction = "in"
                counterparty_wallet = None
            elif transaction_type == 'transfer':
                if request.user == transaction.sender:
                    direction = "out"
                    counterparty_wallet = transaction.recipient_wallet_number
                elif request.user == transaction.recipient:
                    direction = "in"
                    counterparty_wallet = transaction.sender_wallet_number
            elif transaction_type == 'withdrawal':
                direction = "out"
                counterparty_wallet = None
            elif transaction_type == 'refund':
                direction = "in"
                counterparty_wallet = None
            
            transaction_data = {
                'type': transaction_type,
                'amount': float(transaction.amount),
                'status': transaction.status,
                'created_at': transaction.created_at.isoformat(),
                'direction': direction,
                'counterparty_wallet': counterparty_wallet,
                'reference': transaction.reference,
                'description': transaction.description,
                'transaction_id': str(transaction.id)
            }
            
            transactions_list.append(transaction_data)
        
        logger.info(
            "Transaction history retrieved",
            user_id=str(request.user.id),
            wallet_id=str(wallet.id),
            wallet_number=wallet.wallet_number,
            total_count=total_count,
            returned_count=len(transactions_list)
        )
        
        response_data = {
            'transactions': transactions_list,
            'pagination': {
                'total': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': has_more
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)