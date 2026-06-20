from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Account, Transaction, FraudAlert, Notification

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['id', 'phone_number', 'address', 'national_id', 'credit_score', 'monthly_income', 'employment_status', 'created_at', 'updated_at']
        read_only_fields = ['credit_score', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']
        read_only_fields = ['id']


class AccountSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Account
        fields = ['id', 'user', 'account_number', 'account_type', 'balance', 'currency', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'account_number', 'created_at', 'updated_at']


class TransactionSerializer(serializers.ModelSerializer):
    sender_account_num = serializers.CharField(source='sender_account.account_number', read_only=True)
    receiver_account_num = serializers.CharField(source='receiver_account.account_number', read_only=True)
    sender_name = serializers.CharField(source='sender_account.user.username', read_only=True)
    receiver_name = serializers.CharField(source='receiver_account.user.username', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'sender_account', 'receiver_account', 'sender_account_num', 'receiver_account_num',
            'sender_name', 'receiver_name', 'amount', 'transaction_type', 'status', 
            'description', 'reference_number', 'ip_address', 'created_at'
        ]
        read_only_fields = ['id', 'reference_number', 'status', 'created_at']


class FraudAlertSerializer(serializers.ModelSerializer):
    transaction = TransactionSerializer(read_only=True)

    class Meta:
        model = FraudAlert
        fields = ['id', 'transaction', 'reason', 'severity', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'notification_type', 'recipient_target', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']
