-- =============================================================================
-- SMART BANKING SYSTEM - ENTERPRISE ORACLE SQL QUERIES (DML / AUDITING / ANALYTICS)
-- =============================================================================
-- This file contains SQL queries designed to generate reports, perform audits,
-- and run real-time analytics such as transaction histories, volume analyses,
-- and fraud pattern detection using Oracle SQL syntax.
-- =============================================================================

-- 1. DETAILED TRANSACTION AUDIT LEDGER
-- Retrieves a transaction statement with human-readable usernames and account types
-- showing deposits, withdrawals, and sender/recipient details.
SELECT 
    t.id AS transaction_number,
    t.reference_number,
    t.created_at AS transaction_time,
    t.transaction_type,
    t.amount,
    t.status,
    -- Sender Details
    sa.account_number AS sender_account,
    su.username AS sender_name,
    -- Receiver Details
    ra.account_number AS receiver_account,
    ru.username AS receiver_name,
    t.description
FROM banking_transaction t
LEFT JOIN banking_account sa ON t.sender_account_id = sa.id
LEFT JOIN auth_user su ON sa.user_id = su.id
LEFT JOIN banking_account ra ON t.receiver_account_id = ra.id
LEFT JOIN auth_user ru ON ra.user_id = ru.id
ORDER BY t.created_at DESC;


-- 2. MONTHLY FINANCIAL SUMMARY BY ACCOUNT TYPE
-- Aggregate metrics showing total transfer amounts, average transaction size, and count
-- grouped by year-month and account type.
SELECT 
    TO_CHAR(t.created_at, 'YYYY-MM') AS report_month,
    a.account_type,
    COUNT(t.id) AS total_transactions,
    SUM(t.amount) AS aggregate_volume,
    AVG(t.amount) AS average_transaction_value,
    MAX(t.amount) AS largest_transaction
FROM banking_transaction t
JOIN banking_account a ON (t.sender_account_id = a.id OR t.receiver_account_id = a.id)
WHERE t.status = 'Success'
GROUP BY TO_CHAR(t.created_at, 'YYYY-MM'), a.account_type
ORDER BY report_month DESC, a.account_type;


-- 3. FRAUD DETECTION: CUMULATIVE VELOCITY ANALYSIS
-- Analytical window function query to flag accounts that have performed transactions
-- exceeding a total of $15,000 within their most recent 3 consecutive transactions.
SELECT 
    transaction_id,
    account_number,
    owner_name,
    amount,
    transaction_time,
    three_tx_rolling_total,
    CASE 
        WHEN three_tx_rolling_total > 15000 THEN 'SUSPICIOUS - VELOCITY CRITICAL'
        ELSE 'NORMAL'
    END AS risk_classification
FROM (
    SELECT 
        t.id AS transaction_id,
        a.account_number,
        u.username AS owner_name,
        t.amount,
        t.created_at AS transaction_time,
        SUM(t.amount) OVER (
            PARTITION BY a.id 
            ORDER BY t.created_at 
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS three_tx_rolling_total
    FROM banking_transaction t
    JOIN banking_account a ON t.sender_account_id = a.id
    JOIN auth_user u ON a.user_id = u.id
    WHERE t.transaction_type = 'Transfer' AND t.status = 'Success'
)
ORDER BY transaction_time DESC;


-- 4. SYSTEM HEALTH AND RISK PROFILE
-- Retrieves a high-level summary of active users, total deposits, active loans,
-- and pending fraud alerts for system health dashboards.
SELECT 
    (SELECT COUNT(DISTINCT user_id) FROM banking_account WHERE status = 'Active') AS active_customers,
    (SELECT NVL(SUM(balance), 0) FROM banking_account WHERE account_type IN ('Savings', 'Checking') AND status = 'Active') AS total_deposits,
    (SELECT NVL(SUM(balance), 0) FROM banking_account WHERE account_type = 'Loan' AND status = 'Active') AS outstanding_loans,
    (SELECT COUNT(*) FROM banking_fraud_alert WHERE status = 'Pending') AS pending_fraud_investigations
FROM dual;


-- 5. REPETITIVE HIGH-FREQUENCY TRANSACTION DETECTOR
-- Detects accounts transferring money to the same recipient more than twice 
-- within a single 5-minute interval. Indicates potential double-submit bugs or rapid automation fraud.
SELECT 
    t1.sender_account_id,
    sa.account_number AS sender_acc_num,
    t1.receiver_account_id,
    ra.account_number AS receiver_acc_num,
    COUNT(*) AS rapid_tx_count,
    LISTAGG(t1.id, ', ') WITHIN GROUP (ORDER BY t1.created_at) AS transaction_ids
FROM banking_transaction t1
JOIN banking_transaction t2 ON 
    t1.sender_account_id = t2.sender_account_id 
    AND t1.receiver_account_id = t2.receiver_account_id
    AND t1.id < t2.id
    -- Within 5 minutes (5 / 1440 of a day in Oracle date math)
    AND t2.created_at <= t1.created_at + INTERVAL '5' MINUTE
JOIN banking_account sa ON t1.sender_account_id = sa.id
JOIN banking_account ra ON t1.receiver_account_id = ra.id
WHERE t1.transaction_type = 'Transfer'
GROUP BY t1.sender_account_id, sa.account_number, t1.receiver_account_id, ra.account_number
HAVING COUNT(*) >= 2;
