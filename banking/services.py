from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import math
from .models import Account, Transaction, FraudAlert, Notification

class FraudDetectionEngine:
    @staticmethod
    def evaluate_transaction(sender_account, receiver_account, amount):
        """
        Evaluates a transaction for suspicious patterns.
        Returns a list of dictionaries with fraud alert details: {'reason': str, 'severity': str}
        """
        alerts = []
        
        # 1. Self-transfer check
        if sender_account == receiver_account:
            raise ValidationError("Sender and recipient accounts cannot be the same.")

        # 2. Large Amount Threshold (e.g. >= $10,000)
        if amount >= Decimal('10000.00'):
            alerts.append({
                'reason': f"Transaction amount of ${amount} exceeds the single transfer monitoring limit ($10,000).",
                'severity': 'Medium'
            })

        # 3. Critical Balance Depletion (transferring > 90% of account balance)
        if sender_account.balance > 0:
            depletion_ratio = amount / sender_account.balance
            if depletion_ratio >= Decimal('0.90'):
                alerts.append({
                    'reason': f"Transaction depletes {depletion_ratio*100:.1f}% of the account balance (Threshold: 90%).",
                    'severity': 'Low'
                })

        # 4. Velocity Check (e.g., more than 3 transactions in the last 1 minute)
        one_minute_ago = timezone.now() - timedelta(minutes=1)
        recent_tx_count = Transaction.objects.filter(
            sender_account=sender_account,
            created_at__gte=one_minute_ago,
            status='Success'
        ).count()

        if recent_tx_count >= 3:
            alerts.append({
                'reason': f"High frequency velocity limit exceeded. {recent_tx_count} transfers executed in the last 60 seconds.",
                'severity': 'High'
            })

        return alerts


class LoanPredictor:
    @staticmethod
    def predict_eligibility(credit_score, monthly_income, requested_amount, employment_status, existing_debt):
        """
        Infers loan approval eligibility using a custom Logistic Regression model implemented in pure Python.
        Computes the probability of approval and returns decision metadata.
        """
        # 1. Normalize Inputs
        # Credit score: 300 to 850 range
        x_credit = (credit_score - 300) / 550.0
        
        # Income to Loan Ratio: annual income / requested loan amount
        annual_income = monthly_income * 12
        x_income_loan = float(annual_income / requested_amount) if requested_amount > 0 else 0.0
        # Clip ratio at 2.0 to prevent outlier distortion
        x_income_loan_clipped = min(max(x_income_loan, 0.0), 2.0)
        
        # Debt to Income Ratio: monthly debt / monthly income
        x_debt_income = float(existing_debt / monthly_income) if monthly_income > 0 else (float(existing_debt) if existing_debt > 0 else 0.0)

        # Employment status factor
        if employment_status == 'Employed':
            x_employment = 1.0
        elif employment_status == 'Self-Employed':
            x_employment = 0.4
        else: # Unemployed
            x_employment = -1.5

        # 2. Logistic Regression Equation (Hardcoded weights mimicking training coefficients)
        # Prob = 1 / (1 + exp(-z))
        # z = w0 + w1 * credit + w2 * income_loan + w3 * debt_income + w4 * employment
        w0 = -1.8  # Intercept
        w1 = 3.5   # Credit Score weight (high credit score is highly positive)
        w2 = 2.5   # Income-to-loan weight (higher ratio is positive)
        w3 = -3.2  # Debt-to-income weight (high debt ratio is highly negative)
        w4 = 1.2   # Employment weight (stable employment is positive)

        z = w0 + (w1 * x_credit) + (w2 * x_income_loan_clipped) + (w3 * x_debt_income) + (w4 * x_employment)
        
        # Calculate Sigmoid Probability
        try:
            probability = 1.0 / (1.0 + math.exp(-z))
        except OverflowError:
            probability = 0.0 if z < 0 else 1.0

        approved = probability >= 0.5

        # 3. Generate Analytical Explanations
        positives = []
        negatives = []

        if credit_score >= 700:
            positives.append(f"Excellent credit history (Score: {credit_score}).")
        elif credit_score < 600:
            negatives.append(f"Subprime credit history (Score: {credit_score}). A score above 600 is recommended.")

        if x_income_loan >= 1.5:
            positives.append("Strong annual income capacity relative to the requested loan amount.")
        elif x_income_loan < 0.5:
            negatives.append("Annual income is low relative to the loan amount. Consider requesting a lower amount or extending the term.")

        if x_debt_income > 0.4:
            negatives.append(f"High debt-to-income ratio ({x_debt_income*100:.1f}%). Monthly debt obligations are too high.")
        else:
            positives.append(f"Healthy debt-to-income ratio ({x_debt_income*100:.1f}%).")

        if employment_status == 'Employed':
            positives.append("Stable active employment status.")
        elif employment_status == 'Unemployed':
            negatives.append("Currently unemployed. Regular income sources must be verifiable.")

        # Recommendations based on outcome
        if approved:
            recommendation = "Approved. You are eligible for this loan package. Proceed to final contract signing."
        else:
            if credit_score < 600:
                recommendation = "Improve your credit score by making timely payments and reducing card balances before re-applying."
            elif x_debt_income > 0.4:
                recommendation = "Reduce your existing outstanding debt to lower your monthly debt-to-income ratio."
            else:
                recommendation = "Try applying for a smaller loan principal that matches your monthly income limits."

        return {
            'approved': approved,
            'probability': round(probability * 100, 1),
            'factors': {
                'positives': positives,
                'negatives': negatives
            },
            'recommendation': recommendation
        }


class NotificationDispatcher:
    @staticmethod
    def dispatch_alert(user, title, message, alert_type, target):
        """
        Creates a record in the database for the user to view in their notification center
        and simulates standard console dispatch.
        """
        notif = Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=alert_type,
            recipient_target=target,
            status='Sent'
        )
        # Output simulation logs to console for backend logs
        print(f"\n================ [SIMULATED DISPATCH: {alert_type}] ================")
        print(f"To: {target}")
        print(f"Subject/Title: {title}")
        print(f"Message: {message}")
        print("=================================================================\n")
        return notif


class TransactionService:
    @staticmethod
    def execute_transfer(sender_user, sender_account_num, receiver_account_num, amount, description="", ip_address=None):
        """
        Performs an atomic money transfer between two accounts.
        Integrates validation checks, fraud analysis engine, account suspensions, and logging triggers.
        """
        amount = Decimal(str(amount))
        if amount <= Decimal('0.00'):
            raise ValidationError("Transaction amount must be positive.")

        # 1. Fetch accounts without locking first to perform pre-validation
        try:
            sender_acc = Account.objects.get(account_number=sender_account_num, user=sender_user)
        except Account.DoesNotExist:
            raise ValidationError("Sender account not found or access denied.")

        try:
            receiver_acc = Account.objects.get(account_number=receiver_account_num)
        except Account.DoesNotExist:
            raise ValidationError("Recipient account number is invalid.")

        # Status validation
        if sender_acc.status != 'Active':
            raise ValidationError(f"Transaction denied. Sender account is {sender_acc.status}.")
        if receiver_acc.status != 'Active':
            raise ValidationError(f"Transaction denied. Recipient account is {receiver_acc.status}.")

        # 2. Check Insufficient Funds
        if sender_acc.balance < amount:
            # We want to log the failed transaction to the database
            Transaction.objects.create(
                sender_account=sender_acc,
                receiver_account=receiver_acc,
                amount=amount,
                transaction_type='Transfer',
                status='Failed',
                description=f"Declined: Insufficient funds. {description}",
                ip_address=ip_address
            )
            # Now raise the validation error. It will not be rolled back because it's not in an atomic block!
            raise ValidationError(f"Insufficient funds. Available balance: ${sender_acc.balance}")

        # 3. Fraud Engine checks (Velocity Check, etc.)
        fraud_hits = FraudDetectionEngine.evaluate_transaction(sender_acc, receiver_acc, amount)
        high_severity_fraud = any(hit['severity'] == 'High' for hit in fraud_hits)

        if high_severity_fraud:
            # Suspend account
            sender_acc.status = 'Suspended'
            sender_acc.save()

            # Save failed transaction
            tx = Transaction.objects.create(
                sender_account=sender_acc,
                receiver_account=receiver_acc,
                amount=amount,
                transaction_type='Transfer',
                status='Failed',
                description="SUSPENDED: Suspicious high frequency activity detected.",
                ip_address=ip_address
            )

            # Log Fraud Alerts
            for hit in fraud_hits:
                if hit['severity'] == 'High':
                    FraudAlert.objects.create(
                        transaction=tx,
                        reason=hit['reason'],
                        severity=hit['severity'],
                        status='Pending'
                    )

            # Dispatch alerts
            email_target = sender_user.email or f"{sender_user.username}@mockbank.com"
            NotificationDispatcher.dispatch_alert(
                user=sender_user,
                title="URGENT: Bank Account Suspended due to Security Alert",
                message=(
                    f"Hello {sender_user.username},\n\nOur system detected multiple high-frequency transaction attempts "
                    f"on your account {sender_acc.account_number} within a short time. As a security precaution, "
                    f"your account has been SUSPENDED. Please contact customer support immediately."
                ),
                alert_type='Email',
                target=email_target
            )

            raise ValidationError("Transaction blocked. Account suspended due to suspicious high-frequency attempts.")

        # 4. Atomic transaction block to lock rows and execute debit/credit
        with transaction.atomic():
            # Re-fetch and lock accounts to prevent race conditions (double-spends)
            sender_acc_locked = Account.objects.select_for_update().get(id=sender_acc.id)
            receiver_acc_locked = Account.objects.select_for_update().get(id=receiver_acc.id)

            # Double check status and balance just in case it changed between step 1 and step 4
            if sender_acc_locked.status != 'Active' or receiver_acc_locked.status != 'Active':
                raise ValidationError("Transaction denied. One or both accounts are inactive.")
            if sender_acc_locked.balance < amount:
                raise ValidationError(f"Insufficient funds. Available balance: ${sender_acc_locked.balance}")

            # Deduct and credit
            sender_acc_locked.balance -= amount
            receiver_acc_locked.balance += amount
            sender_acc_locked.save()
            receiver_acc_locked.save()

            # Create successful (or flagged) transaction
            tx_status = 'Flagged' if len(fraud_hits) > 0 else 'Success'
            tx_description = description if description else f"Transfer to {receiver_acc_locked.account_number}"

            tx = Transaction.objects.create(
                sender_account=sender_acc_locked,
                receiver_account=receiver_acc_locked,
                amount=amount,
                transaction_type='Transfer',
                status=tx_status,
                description=tx_description,
                ip_address=ip_address
            )

            # Log Fraud Alerts for flagged transfers
            for hit in fraud_hits:
                FraudAlert.objects.create(
                    transaction=tx,
                    reason=hit['reason'],
                    severity=hit['severity'],
                    status='Pending'
                )

        # 5. Trigger Notifications (Outside transaction block)
        sender_email = sender_user.email or f"{sender_user.username}@mockbank.com"
        sender_phone = getattr(sender_user.profile, 'phone_number', None) or "555-0199"
        
        # Notification for debit (Sender)
        NotificationDispatcher.dispatch_alert(
            user=sender_user,
            title=f"Notification: Debit of ${amount} on Acc {sender_acc_locked.account_number[-4:]}",
            message=(
                f"Dear Customer, your account {sender_acc_locked.account_number} was debited by ${amount} "
                f"for a transfer to account {receiver_acc_locked.account_number}. Reference: {tx.reference_number}."
            ),
            alert_type='Email',
            target=sender_email
        )
        
        # Notification for credit (Receiver)
        receiver_user = receiver_acc_locked.user
        receiver_email = receiver_user.email or f"{receiver_user.username}@mockbank.com"
        NotificationDispatcher.dispatch_alert(
            user=receiver_user,
            title=f"Notification: Credit of ${amount} on Acc {receiver_acc_locked.account_number[-4:]}",
            message=(
                f"Dear Customer, your account {receiver_acc_locked.account_number} was credited by ${amount} "
                f"from account {sender_acc_locked.account_number}. Reference: {tx.reference_number}."
            ),
            alert_type='Email',
            target=receiver_email
        )
        
        if sender_phone:
            NotificationDispatcher.dispatch_alert(
                user=sender_user,
                title="Debit Alert SMS",
                message=f"SmartBank Alert: ${amount} debited from Acc ending {sender_acc_locked.account_number[-4:]}. Ref: {tx.reference_number}.",
                alert_type='SMS',
                target=sender_phone
            )

        return tx
