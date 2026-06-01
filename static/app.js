function toggleSidebar(id) {
    const el = document.getElementById(id);
    const chev = document.getElementById(id.split('-')[0] + '-chev');
    if (el.style.display === 'block') {
        el.style.display = 'none';
        chev.style.transform = 'rotate(0deg)';
    } else {
        el.style.display = 'block';
        chev.style.transform = 'rotate(90deg)';
    }
}

function getCsrfToken() {
    const el = document.querySelector('meta[name="csrf-token"]');
    return el ? el.content : '';
}

function apiFetch(url, options = {}) {
    const opts = { ...options };
    const method = (opts.method || 'GET').toUpperCase();
    const headers = { ...(opts.headers || {}) };
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        const token = getCsrfToken();
        if (token) {
            headers['X-CSRF-Token'] = token;
        }
    }
    opts.headers = headers;
    return fetch(url, opts);
}

function resetMobileMenuState() {
    document.body.classList.remove('sidebar-open');
    document.body.style.overflow = '';

    const dashboardLayout = document.querySelector('.dashboard-layout');
    if (dashboardLayout) dashboardLayout.classList.remove('sidebar-active');
}

function toggleMobileSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    if (!sidebar) return;

    const isOpening = !sidebar.classList.contains('active');
    sidebar.classList.toggle('active');
    if (overlay) overlay.classList.toggle('active');

    if (isOpening) {
        document.body.classList.add('sidebar-open');
        document.body.style.overflow = 'hidden';
        const dashboardLayout = document.querySelector('.dashboard-layout');
        if (dashboardLayout) dashboardLayout.classList.add('sidebar-active');
    } else {
        resetMobileMenuState();
    }
}

// Ensure collapsible menus stay open if a child is active
document.addEventListener("DOMContentLoaded", function() {
    const subs = document.querySelectorAll('.sub-nav');
    subs.forEach(sub => {
        if (sub.querySelector('.active')) {
            sub.style.display = 'block';
            const chevId = sub.id.split('-')[0] + '-chev';
            const chev = document.getElementById(chevId);
            if(chev) chev.style.transform = 'rotate(90deg)';
        }
    });

    // Check URL to show Settings tip
    if (window.location.pathname === '/' && !sessionStorage.getItem('settingsTipShown')) {
        const topbar = document.querySelector('.topbar');
        if(topbar) {
            const tip = document.createElement('div');
            tip.innerHTML = `
                <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid var(--brand-blue); color: var(--brand-blue); padding: 12px 20px; border-radius: 8px; font-size: 14px; display: flex; justify-content: space-between; align-items: center; margin: 20px 20px 0; font-weight: 500;">
                    <span>💡 Tip: You can customize your currency symbol in Settings!</span>
                    <button onclick="this.parentElement.style.display='none';" style="background: none; border: none; color: var(--brand-blue); cursor: pointer; font-size: 16px;">&times;</button>
                </div>
            `;
            topbar.insertAdjacentElement('afterend', tip);
            sessionStorage.setItem('settingsTipShown', 'true');
        }
    }

    // Close mobile sidebar only when a real navigation link is clicked.
    document.querySelectorAll('.sidebar a.nav-item, .sidebar a.nav-sub-item').forEach((item) => {
        item.addEventListener('click', () => {
            const sidebar = document.querySelector('.sidebar');
            const overlay = document.querySelector('.sidebar-overlay');
            if (sidebar && sidebar.classList.contains('active')) {
                sidebar.classList.remove('active');
                if (overlay) overlay.classList.remove('active');
                resetMobileMenuState();
            }
        });
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            resetMobileMenuState();
            const sidebar = document.querySelector('.sidebar');
            const overlay = document.querySelector('.sidebar-overlay');
            if (sidebar) sidebar.classList.remove('active');
            if (overlay) overlay.classList.remove('active');
        }
    });

    // Safety: avoid sticky non-scrollable page after refresh/navigation.
    resetMobileMenuState();
});

function openModal(dateStr) {
    document.getElementById('tx-date').value = dateStr;
    document.getElementById('tx-id').value = '';
    document.getElementById('tx-type').value = 'expense';
    document.getElementById('tx-amount').value = '';
    document.getElementById('tx-name').value = '';
    document.getElementById('receipt-input').value = '';
    setScanStatus('');
    
    document.getElementById('modal-title').innerText = 'Add Transaction';
    document.getElementById('del-btn').style.display = 'none';
    
    updateCatDropdown();
    document.getElementById('side-panel').classList.add('active');
    document.getElementById('panel-overlay').classList.add('active');
}

function openEditModal(id, dateStr, amount, type, name, receipt_path) {
    document.getElementById('tx-id').value = id;
    document.getElementById('tx-date').value = dateStr;
    document.getElementById('tx-type').value = type;
    document.getElementById('tx-amount').value = amount;
    document.getElementById('tx-name').value = name;
    document.getElementById('receipt-input').value = '';
    setScanStatus('');
    
    document.getElementById('modal-title').innerText = 'Edit Transaction';
    document.getElementById('del-btn').style.display = 'block';
    
    updateCatDropdown();
    // Preselect the category if possible. Since we don't have cat saved in tx table properly in original code, we guess based on name for now or just let user reselect.
    
    document.getElementById('side-panel').classList.add('active');
    document.getElementById('panel-overlay').classList.add('active');
}

function closePanel() {
    document.getElementById('side-panel').classList.remove('active');
    document.getElementById('panel-overlay').classList.remove('active');
}

function updateCatDropdown() {
    const type = document.getElementById('tx-type').value;
    const catSelect = document.getElementById('tx-category');
    catSelect.innerHTML = '';
    
    let cats = [];
    if(type === 'expense' && window.expenseCats) cats = window.expenseCats;
    if(type === 'income' && window.incomeCats) cats = window.incomeCats;
    
    cats.forEach(c => {
        let opt = document.createElement('option');
        opt.value = c;
        opt.innerText = c;
        catSelect.appendChild(opt);
    });
}

function setScanStatus(message, isError = false) {
    const el = document.getElementById('scan-status');
    if (!el) return;
    el.innerText = message || '';
    el.style.color = isError ? 'var(--danger)' : 'var(--text-muted)';
}

async function scanReceiptAndFill() {
    const fileInput = document.getElementById('receipt-input');
    const btn = document.getElementById('scan-receipt-btn');
    if (!fileInput || !fileInput.files || !fileInput.files[0]) {
        setScanStatus('Choose a receipt image first.', true);
        return;
    }

    const fd = new FormData();
    fd.append('file', fileInput.files[0]);

    try {
        if (btn) {
            btn.disabled = true;
            btn.innerText = 'Scanning...';
        }
        setScanStatus('Scanning receipt...');
        const res = await apiFetch('/api/receipt/scan', {
            method: 'POST',
            body: fd
        });
        const data = await res.json();
        if (!data.success) {
            setScanStatus(data.message || 'Scan failed.', true);
            return;
        }

        const parsed = data.data || {};
        if (parsed.amount !== null && parsed.amount !== undefined) {
            document.getElementById('tx-amount').value = parsed.amount;
        }
        if (parsed.type) {
            document.getElementById('tx-type').value = parsed.type;
        }
        if (parsed.description) {
            document.getElementById('tx-name').value = parsed.description;
        } else if (parsed.name) {
            document.getElementById('tx-name').value = parsed.name;
        }
        if (parsed.category) {
            const catSelect = document.getElementById('tx-category');
            const options = Array.from(catSelect.options).map(opt => opt.value.toLowerCase());
            const index = options.indexOf(String(parsed.category).toLowerCase());
            if (index >= 0) {
                catSelect.selectedIndex = index;
            }
        }
        setScanStatus('Receipt scanned and fields updated.');
    } catch (err) {
        setScanStatus(`Scan failed: ${err.message}`, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = 'Scan Receipt & Auto Fill';
        }
    }
}

async function uploadReceiptForExpense(expenseId) {
    const receiptInput = document.getElementById('receipt-input');
    if (!receiptInput || !receiptInput.files || !receiptInput.files[0]) return;

    const formData = new FormData();
    formData.append('file', receiptInput.files[0]);

    const res = await apiFetch(`/api/expense/${expenseId}/receipt`, {
        method: 'POST',
        body: formData
    });
    const data = await res.json();
    if (!data.success) {
        throw new Error(data.message || 'Failed to upload receipt');
    }
}

async function saveTransaction(e) {
    e.preventDefault();
    const id = document.getElementById('tx-id').value;
    const formData = new FormData(document.getElementById('tx-form'));
    
    let url = '/api/expense';
    let method = 'POST';
    
    if (id) {
        url = `/api/expense/${id}`;
        method = 'PUT';
    }

    const payload = {};
    formData.forEach((value, key) => payload[key] = value);
    payload.is_recurring = document.getElementById('tx-recurring') ? document.getElementById('tx-recurring').checked : false;

    try {
        const res = await apiFetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) {
            alert('Error saving transaction: ' + (data.message || 'Unknown error'));
            return;
        }

        const expenseId = id || data.id;
        await uploadReceiptForExpense(expenseId);
        window.location.reload();
    } catch (err) {
        alert('Error saving transaction: ' + err.message);
    }
}

function deleteExpense(id) {
    if(!confirm('Are you sure you want to delete this transaction?')) return;
    
    apiFetch(`/api/expense/${id}`, {
        method: 'DELETE'
    }).then(res => res.json()).then(data => {
        if(data.success) {
            window.location.reload();
        } else {
            alert('Error deleting');
        }
    });
}

function deleteCurrentTransaction() {
    const id = document.getElementById('tx-id').value;
    if(id) {
        deleteExpense(id);
    }
}

// Authentication
if (document.getElementById('auth-form')) {
    let isLogin = true;
    const authForm = document.getElementById('auth-form');
    const formTitle = document.getElementById('form-title');
    const formSubtitle = document.getElementById('form-subtitle');
    const submitLabel = document.getElementById('submit-label');
    const switchLabel = document.getElementById('switch-lbl');
    const switchBtn = document.getElementById('switch-btn');
    const errorEl = document.getElementById('error-msg');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirm-password');
    const confirmGroup = document.getElementById('confirm-group');
    const forgotLink = document.getElementById('forgot-link');
    const passwordToggle = document.getElementById('password-toggle');
    const confirmPasswordToggle = document.getElementById('confirm-password-toggle');

    const wirePasswordToggle = (toggleBtn, inputEl) => {
        if (!toggleBtn || !inputEl) return;
        toggleBtn.addEventListener('click', () => {
            const isHidden = inputEl.type === 'password';
            inputEl.type = isHidden ? 'text' : 'password';
            toggleBtn.classList.toggle('is-visible', isHidden);
            toggleBtn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
            toggleBtn.setAttribute('aria-pressed', isHidden ? 'true' : 'false');
        });
    };

    const resetPasswordToggle = (toggleBtn, inputEl) => {
        if (!inputEl) return;
        inputEl.type = 'password';
        if (!toggleBtn) return;
        toggleBtn.classList.remove('is-visible');
        toggleBtn.setAttribute('aria-label', 'Show password');
        toggleBtn.setAttribute('aria-pressed', 'false');
    };

    const updateAuthMode = (nextIsLogin, clearFields = true) => {
        isLogin = nextIsLogin;

        if (formTitle) formTitle.innerText = isLogin ? 'Welcome back' : 'Create account';
        if (submitLabel) submitLabel.innerText = isLogin ? 'Sign In' : 'Sign Up';
        if (switchLabel) switchLabel.innerText = isLogin ? "Don't have an account?" : 'Already have an account?';
        if (switchBtn) switchBtn.innerText = isLogin ? 'Sign up' : 'Sign in';
        if (formSubtitle) {
            formSubtitle.innerText = isLogin
                ? 'Sign in to continue planning smarter.'
                : 'Create your account to start planning smarter.';
        }
        if (forgotLink) {
            forgotLink.style.display = isLogin ? 'inline' : 'none';
        }
        if (confirmGroup) {
            confirmGroup.style.display = isLogin ? 'none' : 'block';
        }
        if (confirmPasswordInput) {
            confirmPasswordInput.required = !isLogin;
        }

        document.title = `SpendWise - ${isLogin ? 'Sign In' : 'Sign Up'}`;
        if (errorEl) errorEl.style.display = 'none';

        if (clearFields) {
            if (usernameInput) usernameInput.value = '';
            if (passwordInput) passwordInput.value = '';
            if (confirmPasswordInput) confirmPasswordInput.value = '';
        }
        resetPasswordToggle(passwordToggle, passwordInput);
        resetPasswordToggle(confirmPasswordToggle, confirmPasswordInput);
    };

    const authRequest = (url, payload) => {
        return apiFetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(async (res) => {
            const body = await res.json().catch(() => ({}));
            if (!res.ok || !body.success) {
                const msg = body.message || 'Authentication failed';
                throw new Error(msg);
            }
            return body;
        });
    };

    wirePasswordToggle(passwordToggle, passwordInput);
    wirePasswordToggle(confirmPasswordToggle, confirmPasswordInput);

    const signupMode = new URLSearchParams(window.location.search).get('mode') === 'signup';
    updateAuthMode(!signupMode, false);

    if (forgotLink) {
        forgotLink.addEventListener('click', (e) => {
            e.preventDefault();
            alert('Password reset is not live yet. Please contact support to recover access.');
        });
    }
    
    if (switchBtn) {
        switchBtn.addEventListener('click', () => {
            updateAuthMode(!isLogin);
        });
    }

    authForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const u = usernameInput ? usernameInput.value.trim() : '';
        const p = passwordInput ? passwordInput.value : '';
        const cp = confirmPasswordInput ? confirmPasswordInput.value : '';

        if (!isLogin && p !== cp) {
            if (errorEl) {
                errorEl.innerText = 'Passwords do not match.';
                errorEl.style.display = 'block';
            }
            return;
        }

        try {
            const payload = { username: u, password: p };
            const url = isLogin ? '/login' : '/register';
            await authRequest(url, payload);

            if (!isLogin) {
                await authRequest('/login', payload);
            }
            window.location.href = '/';
        } catch (err) {
            if (errorEl) {
                errorEl.innerText = err.message || 'Server error occurred. See console.';
                errorEl.style.display = 'block';
            }
            console.error('Auth error:', err);
        }
    });
}
