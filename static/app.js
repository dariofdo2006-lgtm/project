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

function toggleMobileSidebar() {
    document.querySelector('.sidebar').classList.toggle('active');
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
});

function openModal(dateStr) {
    document.getElementById('tx-date').value = dateStr;
    document.getElementById('tx-id').value = '';
    document.getElementById('tx-type').value = 'expense';
    document.getElementById('tx-amount').value = '';
    document.getElementById('tx-name').value = '';
    document.getElementById('receipt-input').value = '';
    
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

function saveTransaction(e) {
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

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(res => res.json()).then(data => {
        if(data.success) {
            window.location.reload();
        } else {
            alert('Error saving transaction: ' + (data.message || 'Unknown error'));
        }
    }).catch(err => alert('Error saving transaction: ' + err.message));
}

function deleteExpense(id) {
    if(!confirm('Are you sure you want to delete this transaction?')) return;
    
    fetch(`/api/expense/${id}`, {
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
    
    document.getElementById('switch-btn').addEventListener('click', () => {
        isLogin = !isLogin;
        document.getElementById('form-title').innerText = isLogin ? 'Sign In' : 'Sign Up';
        document.getElementById('submit-btn').innerText = isLogin ? 'SIGN IN' : 'SIGN UP';
        document.getElementById('switch-lbl').innerText = isLogin ? "Don't have an account?" : "Already have an account?";
        document.getElementById('switch-btn').innerText = isLogin ? 'Sign up' : 'Sign in';
        document.getElementById('error-msg').style.display = 'none';
        
        // Clear fields
        document.getElementById('username').value = '';
        document.getElementById('password').value = '';
    });

    document.getElementById('auth-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const u = document.getElementById('username').value;
        const p = document.getElementById('password').value;
        
        const url = isLogin ? '/login' : '/register';
        
        fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: u, password: p})
        }).then(res => res.json()).then(data => {
            if(data.success) {
                window.location.href = '/';
            } else {
                const err = document.getElementById('error-msg');
                err.innerText = data.error || 'Authentication failed';
                err.style.display = 'block';
            }
        });
    });
}
