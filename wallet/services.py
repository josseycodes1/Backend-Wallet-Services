import hashlib
import hmac
import json
from django.conf import settings
from django.utils import timezone
from paystackapi.transaction import Transaction as PaystackTransaction
from paystackapi.paystack import Paystack
import structlog

logger = structlog.get_logger(__name__)

paystack = Paystack(secret_key=settings.PAYSTACK_SECRET_KEY)

class PaystackService:
    @staticmethod
    def initialize_transaction(email, amount_kobo, reference=None):
        """Initialize Paystack transaction - amount should be in Kobo"""
        try:
            # Convert to integer to ensure it's in Kobo
            amount_in_kobo = int(amount_kobo)
            
            # Validate minimum amount (100 Kobo = 1 NGN)
            if amount_in_kobo < 100:
                logger.error(
                    "Amount below minimum",
                    email=email,
                    amount_kobo=amount_kobo,
                    minimum=100
                )
                return {
                    'success': False,
                    'message': f'Amount must be at least 100 Kobo (1 NGN). Got: {amount_kobo} Kobo'
                }
            
            response = PaystackTransaction.initialize(
                reference=reference,
                amount=amount_in_kobo,
                email=email,
                callback_url=f"{settings.BASE_URL}/wallet/deposit/verify"
            )
            
            if response['status']:
                logger.info(
                    "Paystack transaction initialized",
                    email=email,
                    amount_kobo=amount_in_kobo,
                    amount_ngn=amount_in_kobo / 100,
                    reference=response['data']['reference']
                )
                return {
                    'success': True,
                    'reference': response['data']['reference'],
                    'authorization_url': response['data']['authorization_url'],
                    'data': response['data']  # Include full response for metadata
                }
            else:
                logger.error(
                    "Paystack initialization failed",
                    email=email,
                    amount_kobo=amount_kobo,
                    message=response.get('message')
                )
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
                
        except ValueError as e:
            logger.error(
                "Invalid amount format",
                email=email,
                amount_kobo=amount_kobo,
                error=str(e)
            )
            return {
                'success': False,
                'message': f'Invalid amount format: {amount_kobo}. Must be an integer in Kobo.'
            }
        except Exception as e:
            logger.error(
                "Paystack initialization error",
                email=email,
                amount_kobo=amount_kobo,
                error=str(e)
            )
            return {
                'success': False,
                'message': f"Payment initialization error: {str(e)}"
            }
    
    @staticmethod
    def initialize_transaction_ngn(email, amount_ngn, reference=None):
        """Alternative method that accepts amount in NGN for backward compatibility"""
        try:
            # Convert NGN to Kobo
            amount_kobo = int(float(amount_ngn) * 100)
            return PaystackService.initialize_transaction(email, amount_kobo, reference)
        except Exception as e:
            logger.error(
                "NGN amount conversion error",
                email=email,
                amount_ngn=amount_ngn,
                error=str(e)
            )
            return {
                'success': False,
                'message': f"Amount conversion error: {str(e)}"
            }
    
    @staticmethod
    def verify_transaction(reference):
        """Verify Paystack transaction"""
        try:
            response = PaystackTransaction.verify(reference)
            
            if response['status'] and response['data']['status'] == 'success':
                logger.info(
                    "Paystack transaction verified successfully",
                    reference=reference,
                    amount_kobo=response['data']['amount'],
                    amount_ngn=response['data']['amount'] / 100
                )
                return {
                    'success': True,
                    'data': response['data'],
                    'status': 'success',
                    'amount_kobo': response['data']['amount'],
                    'amount_ngn': response['data']['amount'] / 100
                }
            else:
                logger.warning(
                    "Paystack transaction verification failed",
                    reference=reference,
                    status=response['data'].get('status')
                )
                return {
                    'success': False,
                    'data': response['data'],
                    'status': response['data'].get('status', 'failed')
                }
                
        except Exception as e:
            logger.error(
                "Paystack verification error",
                reference=reference,
                error=str(e)
            )
            return {
                'success': False,
                'message': f"Transaction verification error: {str(e)}"
            }
    
    @staticmethod
    def verify_webhook_signature(payload, signature):
        """Verify Paystack webhook signature"""
        try:
            # Use PAYSTACK_SECRET_KEY if PAYSTACK_WEBHOOK_SECRET is not set
            secret_key = getattr(settings, 'PAYSTACK_WEBHOOK_SECRET', settings.PAYSTACK_SECRET_KEY)
            secret = secret_key.encode('utf-8')
            
            # Paystack expects the raw request body, not the parsed JSON
            # If payload is already a dict, convert it back to JSON string
            if isinstance(payload, dict):
                payload_str = json.dumps(payload, separators=(',', ':'))
            else:
                payload_str = str(payload)
            
            expected_signature = hmac.new(
                secret,
                payload_str.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            is_valid = hmac.compare_digest(expected_signature, signature)
            logger.info(
                "Webhook signature verification",
                is_valid=is_valid,
                event=payload.get('event') if isinstance(payload, dict) else 'unknown'
            )
            return is_valid
            
        except Exception as e:
            logger.error("Webhook signature verification error", error=str(e))
            return False

class WalletTransferService:
    @staticmethod
    def transfer_funds(sender_wallet, recipient_wallet, amount, description=""):
        """Transfer funds between wallets - amount should be in NGN"""
        from transactions.models import Transaction
        
        try:
            # Validate transfer
            can_transfer, message = sender_wallet.can_transfer(amount)
            if not can_transfer:
                logger.warning(
                    "Transfer validation failed",
                    sender=sender_wallet.wallet_number,
                    recipient=recipient_wallet.wallet_number,
                    amount=amount,
                    reason=message
                )
                return False, message, None
            
            # Create transaction record
            transaction = Transaction.objects.create(
                sender=sender_wallet.user,
                recipient=recipient_wallet.user,
                amount=amount,
                transaction_type='transfer',
                status='pending',
                description=description
            )
            
            # Perform the transfer atomically
            from django.db import transaction as db_transaction
            
            with db_transaction.atomic():
                # Deduct from sender
                sender_wallet.balance -= amount
                sender_wallet.save(update_fields=['balance', 'updated_at'])
                
                # Add to recipient
                recipient_wallet.balance += amount
                recipient_wallet.save(update_fields=['balance', 'updated_at'])
                
                # Update daily spent
                sender_wallet.update_daily_spent(amount)
                
                # Update transaction status
                transaction.status = 'success'
                transaction.save(update_fields=['status', 'updated_at'])
                
                logger.info(
                    "Transfer completed successfully",
                    transaction_id=str(transaction.id),
                    sender=sender_wallet.wallet_number,
                    recipient=recipient_wallet.wallet_number,
                    amount=amount
                )
                
                return True, "Transfer completed successfully", transaction
            
        except Exception as e:
            logger.error(
                "Transfer failed",
                sender=sender_wallet.wallet_number,
                recipient=recipient_wallet.wallet_number,
                amount=amount,
                error=str(e)
            )
            return False, f"Transfer failed: {str(e)}", None