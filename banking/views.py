from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.http import HttpResponse, StreamingHttpResponse
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

import csv
import io
from decimal import Decimal

from .models import UserProfile, Account, Transaction, FraudAlert, Notification
from .serializers import (
    UserSerializer, UserProfileSerializer, AccountSerializer, 
    TransactionSerializer, FraudAlertSerializer, NotificationSerializer
)
from .services import TransactionService, LoanPredictor, NotificationDispatcher

# =============================================================================
# 1. PAGE VIEWS (HTML RENDERING)
# =============================================================================

def index_redirect(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


def login_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'banking/login.html')


@login_required(login_url='login')
def dashboard_page(request):
    # Pass user variables if needed, standard dashboard rendering
    return render(request, 'banking/dashboard.html')


# =============================================================================
# 2. AUTHENTICATION REST ENDPOINTS
# =============================================================================

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def api_register(request):
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')
    phone = request.data.get('phone_number')
    address = request.data.get('address')
    national_id = request.data.get('national_id')
    monthly_income = request.data.get('monthly_income', 0)
    employment_status = request.data.get('employment_status', 'Employed')

    if not username or not password or not email:
        return Response({'error': 'Username, password and email are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists():
        return Response({'error': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email already registered.'}, status=status.HTTP_400_BAD_REQUEST)

    if national_id and UserProfile.objects.filter(national_id=national_id).exists():
        return Response({'error': 'National ID already registered.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Create core user
        user = User.objects.create_user(username=username, email=email, password=password)
        
        # Create user profile with credit score defaults
        credit_score = 680 # default fair starting credit score
        
        UserProfile.objects.create(
            user=user,
            phone_number=phone,
            address=address,
            national_id=national_id,
            credit_score=credit_score,
            monthly_income=Decimal(str(monthly_income)),
            employment_status=employment_status
        )

        # Automatically open a default savings account with a $500 starting bonus
        Account.objects.create(
            user=user,
            account_type='Savings',
            balance=Decimal('500.00'),
            currency='USD'
        )

        # Log in the user session automatically
        login(request, user)
        
        # Dispatch notification welcome email
        NotificationDispatcher.dispatch_alert(
            user=user,
            title="Welcome to SmartBank Enterprise!",
            message=(
                f"Hello {user.username},\n\nWelcome to SmartBank! We have set up your account profile "
                f"and provisioned a Savings Account with a $500.00 promotional balance to get you started.\n\n"
                f"Thank you for choosing us."
            ),
            alert_type='Email',
            target=email
        )

        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({'error': 'Please provide both username and password.'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)
    if user is not None:
        login(request, user)
        # Log successful login
        NotificationDispatcher.dispatch_alert(
            user=user,
            title="Security Alert: Successful Login Detected",
            message=f"A new login session was established for user {username} on {timezone_now_str()}.",
            alert_type='Email',
            target=user.email or f"{username}@mockbank.com"
        )
        return Response(UserSerializer(user).data)
    else:
        return Response({'error': 'Invalid username or password credentials.'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
def api_logout(request):
    logout(request)
    return Response({'message': 'Logged out successfully.'})


# =============================================================================
# 3. ACCOUNT ENDPOINTS
# =============================================================================

class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Open savings or checking account
        account_type = serializer.validated_data.get('account_type')
        if account_type == 'Loan':
            raise ValidationError("Loan accounts cannot be created directly. Please apply via the Loan Eligibility portal.")
        
        serializer.save(user=self.request.user)


@api_view(['GET'])
def lookup_account_owner(request):
    """
    Look up account number and return owner's username for transfer verification.
    """
    account_num = request.query_params.get('account_number')
    if not account_num:
        return Response({'error': 'Account number required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        acc = Account.objects.get(account_number=account_num)
        # Block lookup of self to prevent confusion
        if acc.user == request.user:
            return Response({'error': 'Self-transfer lookup not supported.', 'is_self': True}, status=status.HTTP_200_OK)
            
        if acc.status != 'Active':
            return Response({'error': 'Target account is currently inactive.', 'status': acc.status}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'account_number': acc.account_number,
            'owner_username': acc.user.username,
            'owner_name': f"{acc.user.first_name} {acc.user.last_name}".strip() or acc.user.username,
            'account_type': acc.account_type
        })
    except Account.DoesNotExist:
        return Response({'error': 'Account not found.'}, status=status.HTTP_404_NOT_FOUND)


# =============================================================================
# 4. FUND TRANSFERS
# =============================================================================

@api_view(['POST'])
def execute_funds_transfer(request):
    """
    Execute transfer between accounts using the TransactionService logic.
    """
    sender_account_num = request.data.get('sender_account')
    receiver_account_num = request.data.get('receiver_account')
    amount = request.data.get('amount')
    description = request.data.get('description', '')
    
    # Retrieve client IP
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    if not sender_account_num or not receiver_account_num or not amount:
        return Response({'error': 'Sender account, recipient account, and amount are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tx = TransactionService.execute_transfer(
            sender_user=request.user,
            sender_account_num=sender_account_num,
            receiver_account_num=receiver_account_num,
            amount=amount,
            description=description,
            ip_address=ip
        )
        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)
    except ValidationError as e:
        return Response({'error': str(e.message) if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# 5. TRANSACTION HISTORY & CSV EXPORTER
# =============================================================================

class TransactionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self, request):
        # Retrieve all transactions where user's accounts are sender or receiver
        user_accounts = Account.objects.filter(user=request.user)
        queryset = Transaction.objects.filter(
            Q(sender_account__in=user_accounts) | Q(receiver_account__in=user_accounts)
        )

        # Filters
        account_num = request.query_params.get('account')
        if account_num:
            queryset = queryset.filter(
                Q(sender_account__account_number=account_num) | 
                Q(receiver_account__account_number=account_num)
            )

        tx_type = request.query_params.get('type')
        if tx_type:
            queryset = queryset.filter(transaction_type=tx_type)

        tx_status = request.query_params.get('status')
        if tx_status:
            queryset = queryset.filter(status=tx_status)

        start_date = request.query_params.get('start_date')
        if start_date:
            try:
                queryset = queryset.filter(created_at__date__gte=parse_date(start_date))
            except Exception:
                pass

        end_date = request.query_params.get('end_date')
        if end_date:
            try:
                queryset = queryset.filter(created_at__date__lte=parse_date(end_date))
            except Exception:
                pass

        search_query = request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query) | 
                Q(reference_number__icontains=search_query)
            )

        return queryset.distinct()

    def get(self, request):
        queryset = self.get_queryset(request)
        serializer = TransactionSerializer(queryset, many=True)
        return Response(serializer.data)


@api_view(['GET'])
def export_transactions_csv(request):
    """
    Exports filtered transaction records of the authenticated user to a CSV file.
    """
    user_accounts = Account.objects.filter(user=request.user)
    queryset = Transaction.objects.filter(
        Q(sender_account__in=user_accounts) | Q(receiver_account__in=user_accounts)
    )

    # Replicate query filters
    account_num = request.query_params.get('account')
    if account_num:
        queryset = queryset.filter(Q(sender_account__account_number=account_num) | Q(receiver_account__account_number=account_num))
    
    tx_type = request.query_params.get('type')
    if tx_type:
        queryset = queryset.filter(transaction_type=tx_type)

    tx_status = request.query_params.get('status')
    if tx_status:
        queryset = queryset.filter(status=tx_status)

    start_date = request.query_params.get('start_date')
    if start_date:
        queryset = queryset.filter(created_at__date__gte=parse_date(start_date))
    end_date = request.query_params.get('end_date')
    if end_date:
        queryset = queryset.filter(created_at__date__lte=parse_date(end_date))

    queryset = queryset.distinct().order_by('-created_at')

    # Generate CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="smartbank_statement.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Transaction ID', 'Reference Number', 'Date', 'Type', 'Amount', 
        'Sender Account', 'Sender Name', 'Receiver Account', 'Receiver Name', 'Status', 'Description'
    ])

    for tx in queryset:
        writer.writerow([
            tx.id,
            tx.reference_number,
            tx.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            tx.transaction_type,
            tx.amount,
            tx.sender_account.account_number if tx.sender_account else 'N/A',
            tx.sender_account.user.username if tx.sender_account else 'External/System',
            tx.receiver_account.account_number if tx.receiver_account else 'N/A',
            tx.receiver_account.user.username if tx.receiver_account else 'External/System',
            tx.status,
            tx.description or ''
        ])

    return response


# =============================================================================
# 6. LOAN PORTAL (PREDICTION AND APPLICATION)
# =============================================================================

@api_view(['POST'])
def predict_loan_eligibility(request):
    """
    Calculates approval scoring based on input values.
    """
    requested_amount = request.data.get('amount')
    existing_debt = request.data.get('existing_debt')
    
    # Use profile defaults or inputs
    profile = request.user.profile
    monthly_income = request.data.get('monthly_income', profile.monthly_income)
    credit_score = request.data.get('credit_score', profile.credit_score)
    employment_status = request.data.get('employment_status', profile.employment_status)

    if not requested_amount:
        return Response({'error': 'Loan amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = LoanPredictor.predict_eligibility(
            credit_score=int(credit_score),
            monthly_income=Decimal(str(monthly_income)),
            requested_amount=Decimal(str(requested_amount)),
            employment_status=employment_status,
            existing_debt=Decimal(str(existing_debt or 0))
        )
        return Response(result)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def apply_loan_disbursement(request):
    """
    Applies for a loan. If predictor approves, disburse funds:
    Creates a 'Loan' account (debt liability) and deposits cash into a standard checking account.
    """
    requested_amount = request.data.get('amount')
    existing_debt = request.data.get('existing_debt', 0)
    disbursement_acc_num = request.data.get('disbursement_account')

    profile = request.user.profile
    monthly_income = profile.monthly_income
    credit_score = profile.credit_score
    employment_status = profile.employment_status

    if not requested_amount or not disbursement_acc_num:
        return Response({'error': 'Requested loan amount and disbursement account number are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = Decimal(str(requested_amount))
        
        # Verify disbursement account exists and belongs to the user
        try:
            disburse_acc = Account.objects.get(account_number=disbursement_acc_num, user=request.user, status='Active')
        except Account.DoesNotExist:
            return Response({'error': 'Disbursement account number is invalid or inactive.'}, status=status.HTTP_400_BAD_REQUEST)

        # Run Prediction logic first
        prediction = LoanPredictor.predict_eligibility(
            credit_score=int(credit_score),
            monthly_income=Decimal(str(monthly_income)),
            requested_amount=amount,
            employment_status=employment_status,
            existing_debt=Decimal(str(existing_debt or 0))
        )

        if not prediction['approved']:
            return Response({
                'approved': False,
                'error': "Loan application declined. Review recommendations.",
                'recommendation': prediction['recommendation'],
                'factors': prediction['factors']
            }, status=status.HTTP_400_BAD_REQUEST)

        # Atomically disburse loan:
        with transaction.atomic():
            # 1. Create a Loan Account (Negative/Outstanding liability)
            loan_acc = Account.objects.create(
                user=request.user,
                account_type='Loan',
                balance=amount, # Represents outstanding loan amount
                currency='USD',
                status='Active'
            )
            
            # 2. Add funds to checking account
            disburse_acc.balance += amount
            disburse_acc.save()

            # 3. Log Deposit Transaction for the Checking Account
            tx = Transaction.objects.create(
                receiver_account=disburse_acc,
                amount=amount,
                transaction_type='Deposit',
                status='Success',
                description=f"Approved Loan Disbursement - Reference Account {loan_acc.account_number}",
                ip_address=request.META.get('REMOTE_ADDR')
            )

        # Trigger Alerts
        email = request.user.email or f"{request.user.username}@mockbank.com"
        NotificationDispatcher.dispatch_alert(
            user=request.user,
            title=f"Loan Approved & Disbursed: ${amount}",
            message=(
                f"Congratulations {request.user.username},\n\nYour loan application for ${amount} has been APPROVED "
                f"based on our automated risk evaluation. A loan liability account {loan_acc.account_number} was created. "
                f"The principal has been credited to your transaction account {disburse_acc.account_number}.\n\n"
                f"Ref Tx: {tx.reference_number}"
            ),
            alert_type='Email',
            target=email
        )

        return Response({
            'approved': True,
            'loan_account_number': loan_acc.account_number,
            'disbursed_account_number': disburse_acc.account_number,
            'transaction_reference': tx.reference_number,
            'message': f"Loan approved! ${amount} successfully credited to account {disburse_acc.account_number}."
        })

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# 7. NOTIFICATION AND FRAUD SYSTEM API VIEWS
# =============================================================================

@api_view(['GET'])
def list_user_notifications(request):
    notifications = Notification.objects.filter(user=request.user)
    serializer = NotificationSerializer(notifications, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def list_user_fraud_alerts(request):
    # Find all fraud alerts relating to user's accounts
    user_accounts = Account.objects.filter(user=request.user)
    alerts = FraudAlert.objects.filter(
        Q(transaction__sender_account__in=user_accounts) | 
        Q(transaction__receiver_account__in=user_accounts)
    ).distinct()
    serializer = FraudAlertSerializer(alerts, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def get_user_profile(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['PUT'])
def update_user_profile(request):
    profile = request.user.profile
    
    # Allow updating phone, address, and financial inputs (to test ML eligibility updates!)
    profile.phone_number = request.data.get('phone_number', profile.phone_number)
    profile.address = request.data.get('address', profile.address)
    
    income = request.data.get('monthly_income')
    if income is not None:
        profile.monthly_income = Decimal(str(income))
        
    emp = request.data.get('employment_status')
    if emp is not None:
        profile.employment_status = emp
        
    score = request.data.get('credit_score')
    if score is not None:
        profile.credit_score = int(score)

    try:
        profile.full_clean()
        profile.save()
        
        # Trigger email alerts on settings update
        NotificationDispatcher.dispatch_alert(
            user=request.user,
            title="Profile Contact/Financial Details Updated",
            message="This is a notification to confirm that details on your bank profile were updated successfully.",
            alert_type='Email',
            target=request.user.email or f"{request.user.username}@mockbank.com"
        )
        
        return Response(UserSerializer(request.user).data)
    except ValidationError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# Helper function
def timezone_now_str():
    from django.utils import timezone
    return timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')
