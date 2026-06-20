/* =============================================================================
   SMART BANKING SYSTEM - FRONTEND APP CONTROLLER (app.js)
   ============================================================================= */

// Global state variables
let currentUser = null;
let userAccounts = [];
let transactionsCache = [];
let balanceChart = null;
let lookupTimeout = null;

// Initialize the app on load
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    updateSystemTime();
    setInterval(updateSystemTime, 60000); // Update clock every minute

    // Load initial essential user data
    const loggedIn = await loadUserData();
    if (loggedIn) {
        await loadAccounts();
        await loadOverview();
        // Load notification count in background
        loadNotificationCount();
    }
}

function updateSystemTime() {
    const timeBadge = document.getElementById("system-time-badge");
    if (timeBadge) {
        const options = { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
        timeBadge.textContent = new Date().toLocaleDateString("en-US", options);
    }
}

// =============================================================================
// 1. SPA TAB NAVIGATION
// =============================================================================
function switchTab(tabId) {
    // 1. Update Navigation classes
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach(item => item.classList.remove("active"));
    
    const activeNav = document.getElementById(`nav-${tabId}`);
    if (activeNav) activeNav.classList.add("active");

    // 2. Switch panels
    const panels = document.querySelectorAll(".tab-panel");
    panels.forEach(panel => panel.classList.remove("active"));

    const activePanel = document.getElementById(`panel-${tabId}`);
    if (activePanel) activePanel.classList.add("active");

    // 3. Update Title Header
    const displayTitle = document.getElementById("page-display-title");
    if (displayTitle) {
        displayTitle.textContent = tabId.charAt(0).toUpperCase() + tabId.slice(1) + (tabId === 'loans' ? ' & Credit Portal' : tabId === 'transfer' ? ' & Statements' : ' Overview');
    }

    // 4. Load tab specific data
    if (tabId === 'overview') {
        loadOverview();
    } else if (tabId === 'transfer') {
        loadTransfers();
    } else if (tabId === 'loans') {
        loadLoans();
    } else if (tabId === 'security') {
        loadSecurity();
    } else if (tabId === 'notifications') {
        loadNotifications();
    } else if (tabId === 'settings') {
        loadSettings();
    }
}

// =============================================================================
// 2. DATA LOADERS & REST API FETCHERS
// =============================================================================

async function loadUserData() {
    try {
        const response = await fetch('/api/profile/');
        if (response.status === 403 || response.status === 401) {
            // Not authenticated, redirect to login
            window.location.href = '/login/';
            return false;
        }
        currentUser = await response.json();
        
        // Update user badge in UI
        const usernameDisplay = document.getElementById("sidebar-username");
        const avatarDisplay = document.getElementById("sidebar-avatar");
        if (usernameDisplay) usernameDisplay.textContent = currentUser.username;
        if (avatarDisplay && currentUser.username) {
            avatarDisplay.textContent = currentUser.username.substring(0, 2).toUpperCase();
        }
        return true;
    } catch (e) {
        console.error("Error retrieving user credentials:", e);
        return false;
    }
}

async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts/');
        userAccounts = await response.json();
        renderAccounts();
        populateAccountDropdowns();
    } catch (e) {
        console.error("Error retrieving bank accounts:", e);
    }
}

async function loadOverview() {
    await loadAccounts();
    await fetchTransactions();
    renderRecentTransactions();
    updateBalanceChart();
}

async function loadTransfers() {
    await loadAccounts();
    await fetchTransactions();
    renderFullTransactions();
}

async function loadLoans() {
    // Populate profile read-only details on the loan predictor form
    if (currentUser) {
        document.getElementById("loan-income").value = currentUser.profile.monthly_income;
        document.getElementById("loan-credit").value = currentUser.profile.credit_score;
        document.getElementById("loan-employment").value = currentUser.profile.employment_status;
    }
    
    // Populate checking account options for loan disbursement
    const disburseSelect = document.getElementById("loan-disburse-account");
    if (disburseSelect) {
        disburseSelect.innerHTML = '<option value="">Select checking account for funds</option>';
        const checkingAccounts = userAccounts.filter(acc => acc.account_type === 'Checking' && acc.status === 'Active');
        
        checkingAccounts.forEach(acc => {
            const option = document.createElement("option");
            option.value = acc.account_number;
            option.textContent = `Checking - Acc ${acc.account_number} (Bal: $${acc.balance})`;
            disburseSelect.appendChild(option);
        });
    }
}

async function loadSecurity() {
    try {
        const response = await fetch('/api/fraud/alerts/');
        const alerts = await response.json();
        renderFraudAlerts(alerts);
    } catch (e) {
        console.error("Error loading security audits:", e);
    }
}

async function loadNotifications() {
    try {
        const response = await fetch('/api/notifications/');
        const notifications = await response.json();
        renderNotifications(notifications);
        
        // Mark all as read/hide count
        const badge = document.getElementById("notif-count-badge");
        if (badge) badge.style.display = "none";
    } catch (e) {
        console.error("Error loading notification mailbox:", e);
    }
}

async function loadNotificationCount() {
    try {
        const response = await fetch('/api/notifications/');
        const notifications = await response.json();
        
        const badge = document.getElementById("notif-count-badge");
        if (badge && notifications.length > 0) {
            badge.textContent = notifications.length;
            badge.style.display = "inline-block";
        }
    } catch (e) {
        console.error("Error reading notification badge count:", e);
    }
}

async function loadSettings() {
    if (!currentUser) await loadUserData();
    
    if (currentUser) {
        document.getElementById("set-username").value = currentUser.username;
        document.getElementById("set-email").value = currentUser.email;
        document.getElementById("set-phone").value = currentUser.profile.phone_number || '';
        document.getElementById("set-national-id").value = currentUser.profile.national_id || '';
        document.getElementById("set-address").value = currentUser.profile.address || '';
        document.getElementById("set-income").value = currentUser.profile.monthly_income;
        document.getElementById("set-employment").value = currentUser.profile.employment_status;
        document.getElementById("set-credit").value = currentUser.profile.credit_score;
    }
}

async function fetchTransactions() {
    try {
        const response = await fetch('/api/transactions/');
        transactionsCache = await response.json();
    } catch (e) {
        console.error("Error fetching transactions cache:", e);
    }
}

// =============================================================================
// 3. UI RENDERING LOGIC
// =============================================================================

function renderAccounts() {
    const container = document.getElementById("accounts-container");
    if (!container) return;

    if (userAccounts.length === 0) {
        container.innerHTML = `
            <div style="grid-column: 1/-1; padding: 2rem; text-align: center; color: var(--text-muted);">
                No active accounts found. Open a new savings account using the option above.
            </div>`;
        return;
    }

    container.innerHTML = "";
    userAccounts.forEach(acc => {
        const card = document.createElement("div");
        card.className = `bank-card card-${acc.account_type.toLowerCase()}`;
        
        let typeLabel = acc.account_type;
        if (acc.account_type === 'Savings') typeLabel = 'Savings Card';
        if (acc.account_type === 'Checking') typeLabel = 'Debit Checking';
        if (acc.account_type === 'Loan') typeLabel = 'Loan Liability';

        card.innerHTML = `
            <div class="card-chip"></div>
            <div class="card-type">${typeLabel}</div>
            <div class="card-balance-box">
                <div class="card-label">Available Balance</div>
                <div class="card-balance">$${parseFloat(acc.balance).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
            </div>
            <div class="card-details">
                <span>ACC •••• ${acc.account_number.substring(6)}</span>
                <span>${acc.currency}</span>
            </div>
            <span class="card-status-badge status-${acc.status.toLowerCase()}">${acc.status}</span>
        `;
        container.appendChild(card);
    });
}

function populateAccountDropdowns() {
    const quickSender = document.getElementById("quick-sender");
    const fullSender = document.getElementById("full-sender");

    const populate = (selectElement) => {
        if (!selectElement) return;
        selectElement.innerHTML = '<option value="">Select source account</option>';
        
        // Only transfer from Active Savings or Checking accounts
        const transferable = userAccounts.filter(acc => acc.status === 'Active' && acc.account_type !== 'Loan');
        transferable.forEach(acc => {
            const option = document.createElement("option");
            option.value = acc.account_number;
            option.textContent = `${acc.account_type} Account - Acc ${acc.account_number} (Bal: $${acc.balance})`;
            selectElement.appendChild(option);
        });
    };

    populate(quickSender);
    populate(fullSender);
}

function renderRecentTransactions() {
    const tbody = document.getElementById("recent-transactions-body");
    if (!tbody) return;

    if (transactionsCache.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No historical transactions found.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";
    // Show only the 5 most recent
    const recents = transactionsCache.slice(0, 5);
    recents.forEach(tx => {
        const row = document.createElement("tr");
        const formattedDate = new Date(tx.created_at).toLocaleString('en-US', {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'});
        
        const isDebit = isUserDebit(tx);
        const amountClass = isDebit ? 'amount-debit' : 'amount-credit';
        const amountPrefix = isDebit ? '-' : '+';
        const formattedAmount = `${amountPrefix}$${parseFloat(tx.amount).toFixed(2)}`;

        row.innerHTML = `
            <td><code style="color:var(--accent-blue);">${tx.reference_number}</code></td>
            <td>${formattedDate}</td>
            <td><span class="badge ${tx.transaction_type === 'Transfer' ? 'badge-flagged' : 'badge-success'}">${tx.transaction_type}</span></td>
            <td>${tx.description || 'No Description'}</td>
            <td><span class="badge ${tx.status === 'Success' ? 'badge-success' : tx.status === 'Flagged' ? 'badge-flagged' : 'badge-failed'}">${tx.status}</span></td>
            <td style="text-align: right;" class="${amountClass}">${formattedAmount}</td>
        `;
        tbody.appendChild(row);
    });
}

function renderFullTransactions() {
    const tbody = document.getElementById("full-transactions-body");
    if (!tbody) return;

    if (transactionsCache.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No transactions recorded.</td></tr>`;
        return;
    }

    // This gets filtered dynamically, so let's render the cached list first
    filterTransactions();
}

function renderFraudAlerts(alerts) {
    const container = document.getElementById("fraud-alerts-container");
    if (!container) return;

    if (alerts.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 2rem;">No active fraud alerts detected. System is secure.</div>`;
        return;
    }

    container.innerHTML = "";
    alerts.forEach(alert => {
        const card = document.createElement("div");
        card.className = `glass-container security-alert-card ${alert.severity.toLowerCase()}`;
        
        const date = new Date(alert.created_at).toLocaleString();
        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h4 class="notif-title" style="color: ${alert.severity === 'High' ? 'var(--status-danger)' : alert.severity === 'Medium' ? 'var(--status-warning)' : 'var(--accent-blue)'}">${alert.reason}</h4>
                <span class="badge ${alert.status === 'Pending' ? 'badge-failed' : alert.status === 'Resolved' ? 'badge-success' : 'badge-flagged'}">${alert.status}</span>
            </div>
            <p style="font-size:0.8rem; color:var(--text-secondary); margin-top:0.5rem;">
                Triggered by Transaction Reference: <code>${alert.transaction.reference_number}</code> (${alert.transaction.transaction_type} of $${alert.transaction.amount})
            </p>
            <div class="security-meta">
                <span>Auditor Severity: <strong>${alert.severity}</strong></span>
                <span>${date}</span>
            </div>
        `;
        container.appendChild(card);
    });
}

function renderNotifications(notifications) {
    const container = document.getElementById("notifications-container");
    const countBadge = document.getElementById("inbox-alert-count");
    if (!container) return;

    if (countBadge) countBadge.textContent = `${notifications.length} alert messages`;

    if (notifications.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 3rem;">No alerts recorded in notification history.</div>`;
        return;
    }

    container.innerHTML = "";
    notifications.forEach(notif => {
        const card = document.createElement("div");
        card.className = "glass-container notif-card";
        const date = new Date(notif.created_at).toLocaleString();
        
        card.innerHTML = `
            <div class="notif-header">
                <h3 class="notif-title">${notif.title}</h3>
                <span class="notif-channel">${notif.notification_type} : ${notif.recipient_target}</span>
            </div>
            <div class="notif-message">${notif.message}</div>
            <div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.75rem; text-align:right;">
                Sent on ${date}
            </div>
        `;
        container.appendChild(card);
    });
}

// Helper: Determine if user is debit or credit in a transaction
function isUserDebit(tx) {
    if (tx.transaction_type === 'Withdrawal') return true;
    if (tx.transaction_type === 'Deposit') return false;
    
    // It's a Transfer, check if user owns the sender account
    if (tx.sender_account_num) {
        return userAccounts.some(acc => acc.account_number === tx.sender_account_num);
    }
    return false;
}

// =============================================================================
// 4. FILTER TRANSACTIONS LEDGER
// =============================================================================
function filterTransactions() {
    const tbody = document.getElementById("full-transactions-body");
    if (!tbody) return;

    const searchVal = document.getElementById("filter-search").value.toLowerCase();
    const accVal = document.getElementById("filter-account").value;
    const typeVal = document.getElementById("filter-type").value;
    const statusVal = document.getElementById("filter-status").value;

    let filtered = transactionsCache;

    if (searchVal) {
        filtered = filtered.filter(tx => 
            (tx.description && tx.description.toLowerCase().includes(searchVal)) ||
            tx.reference_number.toLowerCase().includes(searchVal)
        );
    }
    if (accVal) {
        filtered = filtered.filter(tx => 
            tx.sender_account_num === accVal || tx.receiver_account_num === accVal
        );
    }
    if (typeVal) {
        filtered = filtered.filter(tx => tx.transaction_type === typeVal);
    }
    if (statusVal) {
        filtered = filtered.filter(tx => tx.status === statusVal);
    }

    // Populate Account dropdown filter if empty
    const selectFilterAcc = document.getElementById("filter-account");
    if (selectFilterAcc && selectFilterAcc.options.length <= 1) {
        userAccounts.forEach(acc => {
            const opt = document.createElement("option");
            opt.value = acc.account_number;
            opt.textContent = `${acc.account_type} (*${acc.account_number.substring(6)})`;
            selectFilterAcc.appendChild(opt);
        });
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No transaction statements match current filters.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";
    filtered.forEach(tx => {
        const row = document.createElement("tr");
        const date = new Date(tx.created_at).toLocaleString();
        
        const isDebit = isUserDebit(tx);
        const amountClass = isDebit ? 'amount-debit' : 'amount-credit';
        const amountPrefix = isDebit ? '-' : '+';
        const formattedAmount = `${amountPrefix}$${parseFloat(tx.amount).toFixed(2)}`;

        let detailsString = "";
        if (tx.transaction_type === 'Transfer') {
            if (isDebit) {
                detailsString = `Sent to user ${tx.receiver_name || 'external'} (Acc: ${tx.receiver_account_num})`;
            } else {
                detailsString = `Received from user ${tx.sender_name || 'external'} (Acc: ${tx.sender_account_num})`;
            }
        } else {
            detailsString = tx.description || tx.transaction_type;
        }

        row.innerHTML = `
            <td><code style="color:var(--accent-blue);">${tx.reference_number}</code></td>
            <td>${date}</td>
            <td><span class="badge ${tx.transaction_type === 'Transfer' ? 'badge-flagged' : 'badge-success'}">${tx.transaction_type}</span></td>
            <td>${detailsString}</td>
            <td><span class="badge ${tx.status === 'Success' ? 'badge-success' : tx.status === 'Flagged' ? 'badge-flagged' : 'badge-failed'}">${tx.status}</span></td>
            <td style="text-align: right;" class="${amountClass}">${formattedAmount}</td>
        `;
        tbody.appendChild(row);
    });
}

// =============================================================================
// 5. DEBOUNCED RECIPIENT ACCOUNT LOOKUPS
// =============================================================================
function debounceLookup(accountNumber, displayBoxId) {
    const displayBox = document.getElementById(displayBoxId);
    if (!displayBox) return;

    // Reset previous timeout
    clearTimeout(lookupTimeout);
    
    if (accountNumber.length !== 10) {
        displayBox.style.display = 'none';
        displayBox.innerHTML = '';
        return;
    }

    // Set loading
    displayBox.style.display = 'block';
    displayBox.style.background = 'rgba(255, 255, 255, 0.05)';
    displayBox.style.color = 'var(--text-secondary)';
    displayBox.innerHTML = '<div class="loading-spinner" style="width:14px; height:14px; display:inline-block; vertical-align:middle; margin-right:6px;"></div> Looking up account owner...';

    lookupTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/api/accounts/lookup/?account_number=${accountNumber}`);
            const data = await response.json();

            if (response.ok) {
                if (data.is_self) {
                    displayBox.style.background = 'var(--status-warning-bg)';
                    displayBox.style.color = 'var(--status-warning)';
                    displayBox.innerHTML = `⚠️ This is your own account (${data.account_type}).`;
                } else {
                    displayBox.style.background = 'var(--status-success-bg)';
                    displayBox.style.color = 'var(--status-success)';
                    displayBox.innerHTML = `✔️ Recipient Verified: <strong>${data.owner_name}</strong> (${data.account_type})`;
                }
            } else {
                displayBox.style.background = 'var(--status-danger-bg)';
                displayBox.style.color = 'var(--status-danger)';
                displayBox.innerHTML = `❌ Owner lookup failed: ${data.error}`;
            }
        } catch (e) {
            displayBox.style.background = 'var(--status-danger-bg)';
            displayBox.style.color = 'var(--status-danger)';
            displayBox.innerHTML = '❌ Network error during account lookup.';
        }
    }, 450); // 450ms debounce window
}

// =============================================================================
// 6. FORM HANDLERS
// =============================================================================

async function handleQuickTransfer(event) {
    event.preventDefault();
    const sender = document.getElementById("quick-sender").value;
    const receiver = document.getElementById("quick-recipient").value;
    const amount = document.getElementById("quick-amount").value;
    const submitBtn = document.getElementById("quick-transfer-submit");

    if (!sender || !receiver || !amount) return;

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<div class="loading-spinner"></div>';

    try {
        const response = await fetch('/api/transfers/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                sender_account: sender,
                receiver_account: receiver,
                amount: amount,
                description: 'Quick Transfer'
            })
        });

        const data = await response.json();

        if (response.ok) {
            alert(`Transfer Successful! Reference: ${data.reference_number}`);
            document.getElementById("quick-transfer-form").reset();
            document.getElementById("quick-lookup").style.display = 'none';
            await loadOverview();
        } else {
            alert(`Transfer Declined: ${data.error}`);
        }
    } catch (e) {
        alert("Failed to submit transfer due to connection issues.");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Send Transfer";
    }
}

async function handleFullTransfer(event) {
    event.preventDefault();
    const sender = document.getElementById("full-sender").value;
    const receiver = document.getElementById("full-recipient").value;
    const amount = document.getElementById("full-amount").value;
    const desc = document.getElementById("full-desc").value;
    const alertBox = document.getElementById("transfer-alert");
    const submitBtn = document.getElementById("full-transfer-submit");

    if (alertBox) alertBox.style.display = 'none';

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<div class="loading-spinner"></div>';

    try {
        const response = await fetch('/api/transfers/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                sender_account: sender,
                receiver_account: receiver,
                amount: amount,
                description: desc
            })
        });

        const data = await response.json();

        if (response.ok) {
            alert(`Fund Transfer Executed Successfully! Reference: ${data.reference_number}`);
            document.getElementById("full-transfer-form").reset();
            document.getElementById("full-lookup").style.display = 'none';
            await loadTransfers();
        } else {
            if (alertBox) {
                alertBox.textContent = `Declined: ${data.error}`;
                alertBox.style.display = 'block';
            } else {
                alert(`Declined: ${data.error}`);
            }
        }
    } catch (e) {
        alert("Error executing funds transfer.");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Execute Transaction";
    }
}

async function handleCreateAccount(event) {
    event.preventDefault();
    const accountType = document.getElementById("new-acc-type").value;

    try {
        const response = await fetch('/api/accounts/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                account_type: accountType
            })
        });

        if (response.ok) {
            closeNewAccountModal();
            await loadAccounts();
            alert("New banking account provisioned successfully!");
        } else {
            const data = await response.json();
            alert(`Provisioning failed: ${data.error || 'Check parameters'}`);
        }
    } catch (e) {
        alert("Connection error provisioning account.");
    }
}

async function runLoanRiskAnalysis() {
    const amount = document.getElementById("loan-amount").value;
    const debt = document.getElementById("loan-debt").value || 0;
    const alertBox = document.getElementById("loan-alert");

    if (alertBox) alertBox.style.display = 'none';

    if (!amount) {
        alert("Please specify a loan principal amount to analyze.");
        return;
    }

    try {
        const response = await fetch('/api/loans/predict/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                amount: amount,
                existing_debt: debt
            })
        });

        const data = await response.json();
        
        if (response.ok) {
            updateLoanGauge(data.probability, data.approved);
            
            // Render recommendations
            document.getElementById("decision-outcome-text").textContent = data.approved ? "RISK EVALUATION: APPROVED" : "RISK EVALUATION: DECLINED";
            document.getElementById("decision-outcome-text").style.color = data.approved ? "var(--status-success)" : "var(--status-danger)";
            document.getElementById("decision-recommendation-text").textContent = data.recommendation;

            // Build analysis checklist
            const checklist = document.getElementById("checklist-container");
            checklist.innerHTML = "";
            
            data.factors.positives.forEach(f => {
                checklist.innerHTML += `<div class="factor-item"><span class="factor-icon-pos">✓</span><span>${f}</span></div>`;
            });
            data.factors.negatives.forEach(f => {
                checklist.innerHTML += `<div class="factor-item"><span class="factor-icon-neg">✗</span><span>${f}</span></div>`;
            });
        } else {
            alert(`Analysis execution error: ${data.error}`);
        }
    } catch (e) {
        alert("Error executing credit analysis.");
    }
}

async function handleLoanPredict(event) {
    event.preventDefault();
    const amount = document.getElementById("loan-amount").value;
    const debt = document.getElementById("loan-debt").value || 0;
    const disburseAccount = document.getElementById("loan-disburse-account").value;
    const alertBox = document.getElementById("loan-alert");
    const submitBtn = document.getElementById("loan-apply-submit");

    if (alertBox) alertBox.style.display = 'none';

    if (!disburseAccount) {
        alert("Please select an active account for receiving disbursed funds.");
        return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<div class="loading-spinner"></div>';

    try {
        const response = await fetch('/api/loans/apply/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                amount: amount,
                existing_debt: debt,
                disbursement_account: disburseAccount
            })
        });

        const data = await response.json();

        if (response.ok) {
            alert(`Loan Disbursed successfully! Liability Account: ${data.loan_account_number}. Cash deposited to Acc ${data.disbursed_account_number}. Ref: ${data.transaction_reference}`);
            document.getElementById("loan-predict-form").reset();
            resetLoanGauge();
            await loadOverview();
        } else {
            if (alertBox) {
                alertBox.textContent = `Declined: ${data.error} - ${data.recommendation || ''}`;
                alertBox.style.display = 'block';
            } else {
                alert(`Loan Declined: ${data.error}`);
            }
        }
    } catch (e) {
        alert("Error during loan application submission.");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit Application";
    }
}

async function handleProfileUpdate(event) {
    event.preventDefault();
    const phone = document.getElementById("set-phone").value;
    const address = document.getElementById("set-address").value;
    const income = document.getElementById("set-income").value;
    const employment = document.getElementById("set-employment").value;
    const credit = document.getElementById("set-credit").value;
    const alertBox = document.getElementById("settings-alert");
    const submitBtn = document.getElementById("settings-submit-btn");

    if (alertBox) alertBox.style.display = 'none';

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<div class="loading-spinner"></div>';

    try {
        const response = await fetch('/api/profile/update/', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                phone_number: phone,
                address: address,
                monthly_income: income,
                employment_status: employment,
                credit_score: credit
            })
        });

        const data = await response.json();

        if (response.ok) {
            currentUser = data;
            alert("User profile settings and risk parameters updated successfully!");
            await loadSettings();
        } else {
            if (alertBox) {
                alertBox.textContent = `Failed: ${data.error}`;
                alertBox.style.display = 'block';
            }
        }
    } catch (e) {
        alert("Connection error saving profile details.");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Save Configuration Changes";
    }
}

async function handleLogout(event) {
    event.preventDefault();
    try {
        const response = await fetch('/api/auth/logout/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });
        if (response.ok) {
            window.location.href = '/login/';
        }
    } catch (e) {
        console.error("Logout fetch failed", e);
    }
}

// =============================================================================
// 7. LOAN GAUGE COMPONENT
// =============================================================================
function updateLoanGauge(percent, approved) {
    const gauge = document.getElementById("loan-gauge");
    const text = document.getElementById("gauge-score-value");
    if (!gauge || !text) return;

    text.textContent = `${percent}%`;

    // Conic gradient drawing
    const accentColor = approved ? "#05d383" : "#ff4d4d";
    gauge.style.background = `conic-gradient(${accentColor} 0% ${percent}%, #1e293b ${percent}% 100%)`;
}

function resetLoanGauge() {
    updateLoanGauge(0, false);
    document.getElementById("decision-outcome-text").textContent = "Run analysis to inspect decision";
    document.getElementById("decision-outcome-text").style.color = "var(--text-muted)";
    document.getElementById("decision-recommendation-text").textContent = 'Input your loan amount and click "Analyze Risk Odds" to check eligibility before submission.';
    document.getElementById("checklist-container").innerHTML = `<div style="font-size: 0.8rem; color: var(--text-muted); text-align: center;">No analysis run yet</div>`;
}

// =============================================================================
// 8. CHARTJS INTEGRATION
// =============================================================================
function updateBalanceChart() {
    const ctx = document.getElementById('balanceChart');
    if (!ctx) return;

    // Destroy existing chart if it exists to prevent overlay bugs
    if (balanceChart) balanceChart.destroy();

    // Generate Chart Data based on cached transactions
    const dailyBalances = {};
    let currentBalance = 0;
    
    // Calculate total net assets of Savings and Checking accounts
    userAccounts.forEach(acc => {
        if (acc.account_type !== 'Loan') {
            currentBalance += parseFloat(acc.balance);
        }
    });

    // Generate date tags
    const days = 7;
    const dates = [];
    const balances = [];

    for (let i = days - 1; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const dateStr = d.toLocaleDateString('en-US', {month: 'short', day: 'numeric'});
        dates.push(dateStr);
        
        // Simulating trend for dashboard presentation
        let mockDiff = 0;
        // Search transactions that occurred on this day and subtract/add to show graph progress
        const startOfDay = new Date(d.setHours(0,0,0,0)).getTime();
        const endOfDay = new Date(d.setHours(23,59,59,999)).getTime();

        transactionsCache.forEach(tx => {
            const txTime = new Date(tx.created_at).getTime();
            if (txTime >= startOfDay && txTime <= endOfDay && tx.status === 'Success') {
                const amount = parseFloat(tx.amount);
                const isDebit = isUserDebit(tx);
                mockDiff += isDebit ? amount : -amount; // subtract back in time
            }
        });
        
        balances.push(currentBalance);
        currentBalance += mockDiff; // step back
    }

    // reverse balances to show progressive timeline order
    balances.reverse();

    // Chart.js Configuration
    balanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Total Asset Liquidity ($)',
                data: balances,
                borderColor: '#00d2ff',
                backgroundColor: 'rgba(0, 210, 255, 0.05)',
                borderWidth: 2.5,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#00d2ff',
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.02)' },
                    ticks: { color: '#9ca3af', font: { family: 'Inter' } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.02)' },
                    ticks: { color: '#9ca3af', font: { family: 'Inter' } }
                }
            }
        }
    });
}

// =============================================================================
// 9. FRAUD DETECTOR SIMULATORS
// =============================================================================

async function simulateVelocityFraud() {
    if (userAccounts.length === 0) return;
    const activeAccs = userAccounts.filter(acc => acc.status === 'Active' && acc.account_type !== 'Loan');
    
    if (activeAccs.length === 0) {
        alert("You do not have any active transaction accounts left to run tests. Provision one first.");
        return;
    }
    
    const account = activeAccs[0].account_number;
    
    alert("Simulation started. Executing 4 consecutive transfers in rapid succession to trigger velocity defenses...");

    // Fire 4 rapid transfer calls
    for (let i = 1; i <= 4; i++) {
        try {
            const response = await fetch('/api/transfers/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    sender_account: account,
                    receiver_account: '0000000000', // Mock bank system terminal
                    amount: 5.00,
                    description: `Velocity check simulation transfer #${i}`
                })
            });
            const data = await response.json();
            console.log(`Simulation Tx #${i} result:`, data);
            
            if (!response.ok && data.error.includes("suspended")) {
                alert(`Defenses Triggered! Transfer #${i} blocked. Result: ${data.error}`);
                break;
            }
        } catch (e) {
            console.error("Simulation request error", e);
        }
    }

    // reload
    await loadUserData();
    await loadOverview();
}

async function simulateLimitFraud() {
    if (userAccounts.length === 0) return;
    const activeAccs = userAccounts.filter(acc => acc.status === 'Active' && acc.account_type !== 'Loan');
    
    if (activeAccs.length === 0) {
        alert("No active transaction account available to test.");
        return;
    }
    
    const account = activeAccs[0].account_number;
    
    // Add temporary balance to test high value if needed
    alert("Triggering $12,500 Single Transfer limit check. This transaction will trigger a Medium severity Audit Alert.");

    try {
        const response = await fetch('/api/transfers/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                sender_account: account,
                receiver_account: '0000000000',
                amount: 12500.00,
                description: "Simulated high value transaction"
            })
        });
        const data = await response.json();
        
        if (response.ok) {
            alert(`Transfer Completed & FLAGGED: Ref: ${data.reference_number}. Check the Security & Alerts tab to inspect the audit case!`);
        } else {
            alert(`Declined (Ensure you have at least $12,500 in your account): ${data.error}`);
        }
    } catch(e) {
        alert("Simulation failed.");
    }

    await loadOverview();
}

// =============================================================================
// 10. SYSTEM MODALS AND EXPORTERS
// =============================================================================
function openNewAccountModal() {
    const modal = document.getElementById("new-account-modal");
    if (modal) modal.style.display = "flex";
}

function closeNewAccountModal() {
    const modal = document.getElementById("new-account-modal");
    if (modal) modal.style.display = "none";
}

function exportTransactions() {
    const searchVal = document.getElementById("filter-search").value;
    const accVal = document.getElementById("filter-account").value;
    const typeVal = document.getElementById("filter-type").value;
    const statusVal = document.getElementById("filter-status").value;

    let url = '/api/transactions/export/?';
    if (searchVal) url += `search=${encodeURIComponent(searchVal)}&`;
    if (accVal) url += `account=${encodeURIComponent(accVal)}&`;
    if (typeVal) url += `type=${encodeURIComponent(typeVal)}&`;
    if (statusVal) url += `status=${encodeURIComponent(statusVal)}&`;

    window.open(url, '_blank');
}

// Helper: Read cookie value
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
