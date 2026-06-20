from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal

from .models import Account, Transaction, UserProfile, FraudAlert
from .services import TransactionService, LoanPredictor, FraudDetectionEngine

# Create your tests here.

class SmartBankingTestCase(TestCase):
    def setUp(self):
        # 1. Create default users
        self.user1 = User.objects.create_user(username='alice', email='alice@smartbank.com', password='Password123')
        self.user2 = User.objects.create_user(username='bob', email='bob@smartbank.com', password='Password123')
        
        # Create UserProfiles
        self.profile1 = UserProfile.objects.create(
            user=self.user1,
            phone_number='555-0111',
            national_id='NAT-1111',
            credit_score=720,
            monthly_income=Decimal('6000.00'),
            employment_status='Employed'
        )
        
        self.profile2 = UserProfile.objects.create(
            user=self.user2,
            phone_number='555-0222',
            national_id='NAT-2222',
            credit_score=550,
            monthly_income=Decimal('2000.00'),
            employment_status='Unemployed'
        )

        # 2. Provision Accounts
        self.alice_savings = Account.objects.create(
            user=self.user1,
            account_type='Savings',
            balance=Decimal('2500.00'),
            status='Active'
        )
        self.alice_checking = Account.objects.create(
            user=self.user1,
            account_type='Checking',
            balance=Decimal('500.00'),
            status='Active'
        )
        self.bob_checking = Account.objects.create(
            user=self.user2,
            account_type='Checking',
            balance=Decimal('100.00'),
            status='Active'
        )

    def test_account_creation_auto_generation(self):
        """Verify that account numbers are auto-generated and unique."""
        self.assertIsNotNone(self.alice_savings.account_number)
        self.assertEqual(len(self.alice_savings.account_number), 10)
        self.assertNotEqual(self.alice_savings.account_number, self.alice_checking.account_number)

    def test_successful_money_transfer(self):
        """Test standard atomic fund transfer executes successfully."""
        initial_alice_bal = self.alice_savings.balance
        initial_bob_bal = self.bob_checking.balance
        transfer_amount = Decimal('400.00')

        tx = TransactionService.execute_transfer(
            sender_user=self.user1,
            sender_account_num=self.alice_savings.account_number,
            receiver_account_num=self.bob_checking.account_number,
            amount=transfer_amount,
            description="Rent payment",
            ip_address="127.0.0.1"
        )

        # Reload balances
        self.alice_savings.refresh_from_db()
        self.bob_checking.refresh_from_db()

        self.assertEqual(self.alice_savings.balance, initial_alice_bal - transfer_amount)
        self.assertEqual(self.bob_checking.balance, initial_bob_bal + transfer_amount)
        self.assertEqual(tx.status, 'Success')
        self.assertEqual(tx.transaction_type, 'Transfer')

    def test_insufficient_funds_transfer(self):
        """Verify that a transfer fails when sender has insufficient funds and logs a failed transaction."""
        transfer_amount = Decimal('10000.00') # Exceeds Alice's balance

        with self.assertRaises(ValidationError):
            TransactionService.execute_transfer(
                sender_user=self.user1,
                sender_account_num=self.alice_checking.account_number,
                receiver_account_num=self.bob_checking.account_number,
                amount=transfer_amount
            )

        # Confirm failed transaction record is saved
        failed_txs = Transaction.objects.filter(
            sender_account=self.alice_checking,
            receiver_account=self.bob_checking,
            status='Failed'
        )
        self.assertEqual(failed_txs.count(), 1)
        self.assertIn("Insufficient funds", failed_txs.first().description)

    def test_loan_eligibility_ml_predictions(self):
        """Test loan risk calculations for credit scores and incomes."""
        # Scenario A: Good credit, stable income -> Should Approve
        prediction_good = LoanPredictor.predict_eligibility(
            credit_score=750,
            monthly_income=Decimal('7000.00'),
            requested_amount=Decimal('15000.00'),
            employment_status='Employed',
            existing_debt=Decimal('300.00')
        )
        self.assertTrue(prediction_good['approved'])
        self.assertGreaterEqual(prediction_good['probability'], 50.0)

        # Scenario B: Low credit score, unemployed -> Should Decline
        prediction_bad = LoanPredictor.predict_eligibility(
            credit_score=500,
            monthly_income=Decimal('1500.00'),
            requested_amount=Decimal('30000.00'),
            employment_status='Unemployed',
            existing_debt=Decimal('800.00')
        )
        self.assertFalse(prediction_bad['approved'])
        self.assertLess(prediction_bad['probability'], 50.0)

    def test_fraud_high_frequency_velocity_lockout(self):
        """Assert that executing 4 transfers in rapid succession triggers velocity checks, suspends account, and blocks transaction."""
        # Execute 3 transactions successfully
        for i in range(3):
            TransactionService.execute_transfer(
                sender_user=self.user1,
                sender_account_num=self.alice_savings.account_number,
                receiver_account_num=self.bob_checking.account_number,
                amount=Decimal('10.00'),
                description=f"Transfer #{i+1}"
            )

        # The 4th rapid transaction should fail, raise error, and suspend Alice's savings account
        with self.assertRaises(ValidationError) as context:
            TransactionService.execute_transfer(
                sender_user=self.user1,
                sender_account_num=self.alice_savings.account_number,
                receiver_account_num=self.bob_checking.account_number,
                amount=Decimal('10.00'),
                description="Transfer #4"
            )

        self.assertIn("blocked", str(context.exception))
        
        # Verify account status
        self.alice_savings.refresh_from_db()
        self.assertEqual(self.alice_savings.status, 'Suspended')

        # Verify high severity fraud alert log
        velocity_alert = FraudAlert.objects.filter(
            severity='High',
            status='Pending',
            reason__icontains='velocity'
        )
        self.assertTrue(velocity_alert.exists())
