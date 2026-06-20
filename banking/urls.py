from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet, basename='account')

urlpatterns = [
    # Page views
    path('', views.index_redirect, name='index'),
    path('login/', views.login_page, name='login'),
    path('dashboard/', views.dashboard_page, name='dashboard'),
    
    # REST API views
    path('api/auth/register/', views.api_register, name='api_register'),
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),
    path('api/profile/', views.get_user_profile, name='api_profile'),
    path('api/profile/update/', views.update_user_profile, name='api_profile_update'),
    path('api/accounts/lookup/', views.lookup_account_owner, name='api_accounts_lookup'),
    path('api/transfers/', views.execute_funds_transfer, name='api_transfers'),
    path('api/transactions/', views.TransactionListView.as_view(), name='api_transactions'),
    path('api/transactions/export/', views.export_transactions_csv, name='api_transactions_export'),
    path('api/loans/predict/', views.predict_loan_eligibility, name='api_loans_predict'),
    path('api/loans/apply/', views.apply_loan_disbursement, name='api_loans_apply'),
    path('api/notifications/', views.list_user_notifications, name='api_notifications'),
    path('api/fraud/alerts/', views.list_user_fraud_alerts, name='api_fraud_alerts'),
    
    # Router endpoints (accounts ViewSet)
    path('api/', include(router.urls)),
]
