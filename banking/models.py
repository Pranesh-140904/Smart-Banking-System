from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import random
import string

# Create your models here.

class UserProfile(models.Model):
    EMPLOYMENT_CHOICES = [
        ('Employed', 'Employed'),
        ('Self-Employed', 'Self-Employed'),
        ('Unemployed', 'Unemployed'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    national_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    credit_score = models.IntegerField(
        default=600,
        validators=[MinValueValidator(300), MaxValueValidator(850)]
    )
    monthly_income = models.DecimalField(
        default=0.00,
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.00)]
    )
    employment_status = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_CHOICES,
        default='Employed'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


class Account(models.Model):
    ACCOUNT_TYPES = [
        ('Savings', 'Savings'),
        ('Checking', 'Checking'),
        ('Loan', 'Loan'),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Suspended', 'Suspended'),
        ('Closed', 'Closed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    account_number = models.CharField(max_length=10, unique=True, blank=True)
    account_type = models.CharField(max_length=15, choices=ACCOUNT_TYPES)
    balance = models.DecimalField(
        default=0.00,
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(0.00)]
    )
    currency = models.CharField(default='USD', max_length=3)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['account_number']),
        ]

    def save(self, *args, **kwargs):
        if not self.account_number:
            # Generate a unique 10-digit account number starting with a random bank routing digit
            while True:
                num = "".join(random.choices(string.digits, k=10))
                if not Account.objects.filter(account_number=num).exists():
                    self.account_number = num
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.account_type} ({self.account_number}) - ${self.balance}"


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('Deposit', 'Deposit'),
        ('Withdrawal', 'Withdrawal'),
        ('Transfer', 'Transfer'),
    ]

    STATUS_CHOICES = [
        ('Success', 'Success'),
        ('Failed', 'Failed'),
        ('Flagged', 'Flagged'),
    ]

    sender_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_transactions'
    )
    receiver_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_transactions'
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Success')
    description = models.CharField(max_length=255, blank=True, null=True)
    reference_number = models.CharField(max_length=50, unique=True, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender_account']),
            models.Index(fields=['receiver_account']),
            models.Index(fields=['created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.reference_number:
            while True:
                ref = "TXN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
                if not Transaction.objects.filter(reference_number=ref).exists():
                    self.reference_number = ref
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Tx {self.reference_number}: {self.transaction_type} of ${self.amount} ({self.status})"


class FraudAlert(models.Model):
    SEVERITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Resolved', 'Resolved'),
        ('False Alarm', 'False Alarm'),
    ]

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='fraud_alerts')
    reason = models.CharField(max_length=255)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='Low')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Fraud Alert: {self.reason} ({self.severity}) - Status: {self.status}"


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('Email', 'Email'),
        ('SMS', 'SMS'),
    ]

    STATUS_CHOICES = [
        ('Sent', 'Sent'),
        ('Failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=100)
    message = models.TextField()
    notification_type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES)
    recipient_target = models.CharField(max_length=100)  # Email address or phone number
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Sent')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.notification_type} to {self.recipient_target}: {self.title}"
