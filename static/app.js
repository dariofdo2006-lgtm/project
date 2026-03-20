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
        
        // Add headers
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].forEach(d => {
            calGrid.innerHTML += `<div style="text-align:center;color:var(--text-muted);font-size:12px;font-weight:bold;">${d}</div>`;
        });

        // Determine first day of month (0 = Sun, 1 = Mon...)
        let firstDay = new Date(window.CURRENT_YEAR, window.CURRENT_MONTH - 1, 1).getDay();
        // Convert to Mon=0 start
        firstDay = firstDay === 0 ? 6 : firstDay - 1;

        // Blanks before start
        for(let i=0; i<firstDay; i++) {
            calGrid.innerHTML += `<div></div>`;
        }

        // Days
        for(let day=1; day<=daysInMonth; day++) {
            const dateStr = `${window.CURRENT_YEAR}-${String(window.CURRENT_MONTH).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const isSelected = dateStr === window.SELECTED_DATE;
            const style = isSelected ? "background: white; color: black;" : "background: black; color: white;";
            
            calGrid.innerHTML += `
                <div style="${style} border: 1px solid var(--border-dark); border-radius: 8px; padding: 10px; cursor: pointer; min-height: 50px;" 
                     onclick="window.location.href='/?year=${window.CURRENT_YEAR}&month=${window.CURRENT_MONTH}&date=${dateStr}'">
                    <div style="font-weight: bold;">${day}</div>
                </div>
            `;
        }
    }
});

function changeMonth(delta) {
    let y = window.CURRENT_YEAR;
    let m = window.CURRENT_MONTH + delta;
    if (m > 12) { m = 1; y++; }
    if (m < 1) { m = 12; y--; }
    window.location.href = `/?year=${y}&month=${m}`;
}

function openAddModal() {
    document.getElementById('add-modal').classList.add('active');
}

function closeAddModal() {
    document.getElementById('add-modal').classList.remove('active');
}

async function saveExpense() {
    const date = document.getElementById('expense-date').value;
    const amount = document.getElementById('expense-amount').value;
    const category = document.getElementById('expense-category').value;
    const name = document.getElementById('expense-name').value;

    const res = await fetch("/api/expense", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, amount, category, name })
    });
    if(res.ok) window.location.reload();
}

async function deleteExpense(id) {
    if(confirm("Delete this transaction?")) {
        const res = await fetch(`/api/expense/${id}`, { method: "DELETE" });
        if(res.ok) window.location.reload();
    }
}
