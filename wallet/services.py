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
    def initialize_transaction(email, amount, reference=None):
        """Initialize Paystack transaction"""
        try:
           
            amount_in_kobo = int(float(amount) * 100)
            
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
                    amount=amount,
                    reference=response['data']['reference']
                )
                return {
                    'success': True,
                    'reference': response['data']['reference'],
                    'authorization_url': response['data']['authorization_url']
                }
            else:
                logger.error(
                    "Paystack initialization failed",
                    email=email,
                    amount=amount,
                    message=response.get('message')
                )
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
                
        except Exception as e:
            logger.error(
                "Paystack initialization error",
                email=email,
                amount=amount,
                error=str(e)
            )
            return {
                'success': False,
                'message': f"Payment initialization error: {str(e)}"
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
                    amount=response['data']['amount']
                )
                return {
                    'success': True,
                    'data': response['data'],
                    'status': 'success'
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
            secret = settings.PAYSTACK_WEBHOOK_SECRET.encode('utf-8')
            expected_signature = hmac.new(
                secret,
                json.dumps(payload, separators=(',', ':')).encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            is_valid = hmac.compare_digest(expected_signature, signature)
            logger.info(
                "Webhook signature verification",
                is_valid=is_valid,
                event=payload.get('event')
            )
            return is_valid
            
        except Exception as e:
            logger.error("Webhook signature verification error", error=str(e))
            return False

class WalletTransferService:
    @staticmethod
    def transfer_funds(sender_wallet, recipient_wallet, amount, description=""):
        """Transfer funds between wallets"""
        from transactions.models import Transaction
        
        try:
            
            can_transfer, message = sender_wallet.can_transfer(amount)
            if not can_transfer:
                logger.warning(
                    "Transfer validation failed",
                    sender=sender_wallet.wallet_number,
                    recipient=recipient_wallet.wallet_number,
                    amount=amount,
                    reason=message
                )
                return False, message
            
          
            transaction = Transaction.objects.create(
                sender=sender_wallet.user,
                recipient=recipient_wallet.user,
                amount=amount,
                transaction_type='transfer',
                status='pending',
                description=description
            )
            
            
            from django.db import transaction as db_transaction
            
            with db_transaction.atomic():
                
                sender_wallet.balance -= amount
                sender_wallet.save(update_fields=['balance', 'updated_at'])
                
                
                recipient_wallet.balance += amount
                recipient_wallet.save(update_fields=['balance', 'updated_at'])
                
                
                sender_wallet.update_daily_spent(amount)
                
               
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