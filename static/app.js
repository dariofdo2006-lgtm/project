document.addEventListener("DOMContentLoaded", () => {
    // --- LOGIN PAGE LOGIC ---
    const authForm = document.getElementById("auth-form");
    if (authForm) {
        let isLoginMode = true;
        const switchBtn = document.getElementById("switch-btn");
        
        switchBtn.addEventListener("click", () => {
            isLoginMode = !isLoginMode;
            document.getElementById("form-title").innerText = isLoginMode ? "Sign In" : "Create Account";
            document.getElementById("submit-btn").innerText = isLoginMode ? "SIGN IN" : "SIGN UP";
            document.getElementById("switch-lbl").innerText = isLoginMode ? "Don't have an account?" : "Already have an account?";
            switchBtn.innerText = isLoginMode ? "Sign up" : "Sign In";
        });

        authForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const username = document.getElementById("username").value;
            const password = document.getElementById("password").value;
            const endpoint = isLoginMode ? "/login" : "/register";

            const res = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            
            const errorMsg = document.getElementById("error-msg");
            if (data.success) {
                if (!isLoginMode) {
                    errorMsg.style.display = "block";
                    errorMsg.style.color = "var(--success)";
                    errorMsg.innerText = "Account created! You can now log in.";
                    setTimeout(() => switchBtn.click(), 1500);
                } else {
                    sessionStorage.removeItem('settingsTipShown');
                    window.location.href = "/";
                }
            } else {
                errorMsg.style.display = "block";
                errorMsg.style.color = "var(--danger)";
                errorMsg.innerText = data.message;
            }
        });
    }

    // --- DASHBOARD LOGIC ---
    const calGrid = document.getElementById("calendar-grid");
    if (calGrid && window.CURRENT_YEAR) {
        // Draw basic days grid
        const daysInMonth = new Date(window.CURRENT_YEAR, window.CURRENT_MONTH, 0).getDate();
        calGrid.innerHTML = "";
        
        calGrid.className = 'calendar-grid';

        // Add headers
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].forEach(d => {
            calGrid.innerHTML += `<div class="calendar-day-header">${d}</div>`;
        });

        // Determine first day of month (0 = Sun, 1 = Mon...)
        let firstDay = new Date(window.CURRENT_YEAR, window.CURRENT_MONTH - 1, 1).getDay();
        // Convert to Mon=0 start
        firstDay = firstDay === 0 ? 6 : firstDay - 1;

        // Blanks before start
        for(let i=0; i<firstDay; i++) {
            calGrid.innerHTML += `<div class="calendar-day empty"></div>`;
        }
        
        // Find today
        const today = new Date();
        const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

        // Days
        for(let day=1; day<=daysInMonth; day++) {
            const dateStr = `${window.CURRENT_YEAR}-${String(window.CURRENT_MONTH).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const isSelected = dateStr === window.SELECTED_DATE;
            const isToday = dateStr === todayStr;
            
            let classes = 'calendar-day';
            if (isSelected) classes += ' selected';
            if (isToday) classes += ' today';
            
            calGrid.innerHTML += `
                <div class="${classes}" onclick="window.location.href='/?year=${window.CURRENT_YEAR}&month=${window.CURRENT_MONTH}&date=${dateStr}'">
                    <div class="calendar-day-num">${day}</div>
                </div>
            `;
        }
    }
    // Allow closing modals safely by clicking outside
    document.addEventListener('click', (e) => {
        if (e.target && e.target.classList && e.target.classList.contains('side-panel-overlay')) {
            e.target.classList.remove('active');
            const panel = e.target.querySelector('.side-panel');
            if (panel) panel.classList.remove('active');
        }
    });

    // Support ESC key to safely exit overlays and sidemenu
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.side-panel-overlay.active, .side-panel.active, .sidebar.active').forEach(el => {
                el.classList.remove('active');
            });
        }
    });


});

function changeMonth(delta) {
    let y = window.CURRENT_YEAR;
    let m = window.CURRENT_MONTH + delta;
    if (m > 12) { m = 1; y++; }
    if (m < 1) { m = 12; y--; }
    window.location.href = `/?year=${y}&month=${m}`;
}

function openAddModal() {
    const editIdEl = document.getElementById('edit-expense-id');
    if (editIdEl) editIdEl.value = '';
    document.getElementById('expense-date').value = window.SELECTED_DATE || new Date().toISOString().split('T')[0];
    document.getElementById('expense-amount').value = '';
    document.getElementById('expense-name').value = '';
    
    const titleEl = document.getElementById('modal-title');
    if (titleEl) titleEl.innerText = "Add Transaction";
    
    const recEl = document.getElementById('expense-recurring');
    if (recEl) recEl.checked = false;
    
    document.getElementById('add-modal-overlay').classList.add('active');
    document.getElementById('add-modal-panel').classList.add('active');
}

function openEditModal(id, date, amount, category, name, is_recurring = 0) {
    document.getElementById('edit-expense-id').value = id;
    document.getElementById('expense-date').value = date;
    document.getElementById('expense-amount').value = parseFloat(amount).toFixed(2);
    document.getElementById('expense-category').value = category;
    document.getElementById('expense-name').value = name;
    
    const recEl = document.getElementById('expense-recurring');
    if (recEl) recEl.checked = !!is_recurring;
    
    document.getElementById('modal-title').innerText = "Edit Transaction";
    document.getElementById('add-modal-overlay').classList.add('active');
    document.getElementById('add-modal-panel').classList.add('active');
}

function closeAddModal() {
    document.getElementById('add-modal-panel').classList.remove('active');
    setTimeout(() => {
        document.getElementById('add-modal-overlay').classList.remove('active');
    }, 300); // Wait for slide animation
}

async function saveExpense() {
    const editIdEl = document.getElementById('edit-expense-id');
    const id = editIdEl ? editIdEl.value : '';
    const date = document.getElementById('expense-date').value;
    const amount = document.getElementById('expense-amount').value;
    const category = document.getElementById('expense-category').value;
    const name = document.getElementById('expense-name').value;
    
    const recEl = document.getElementById('expense-recurring');
    const is_recurring = recEl ? recEl.checked : false;

    const endpoint = id ? `/api/expense/${id}` : "/api/expense";
    const method = id ? "PUT" : "POST";

    const res = await fetch(endpoint, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, amount, category, name, is_recurring })
    });
    if(res.ok) {
        const data = await res.json();
        const expenseId = id || data.id;
        const fileInput = document.getElementById('expense-receipt');
        if (fileInput && fileInput.files.length > 0) {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            await fetch(`/api/expense/${expenseId}/receipt`, {
                method: "POST",
                body: formData
            });
        }
        window.location.reload();
    } else {
        try {
            const errData = await res.json();
            alert(errData.message || "Failed to save transaction.");
        } catch(e) {
            alert("Failed to save transaction. Please check your inputs.");
        }
    }
}

async function deleteExpense(id) {
    if(confirm("Delete this transaction?")) {
        const res = await fetch(`/api/expense/${id}`, { method: "DELETE" });
        if(res.ok) window.location.reload();
    }
}

function toggleSidebar(id) {
    const el = document.getElementById(id);
    const chev = document.getElementById(id.replace('-sub', '-chev'));
    if (el.style.display === 'block') {
        el.style.display = 'none';
        if (chev) chev.innerText = '›';
    } else {
        el.style.display = 'block';
        if (chev) chev.innerText = '˅';
    }
}

function toggleMobileSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('active');
    }
}

