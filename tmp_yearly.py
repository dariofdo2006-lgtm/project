import customtkinter as ctk
import sqlite3
import calendar
from datetime import datetime
from tkinter import filedialog, messagebox

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

COLOR_BG = "#000000"
COLOR_PANEL = "#0A0A0A"
COLOR_NAV = "#000000"
COLOR_TEXT = "#FFFFFF"
COLOR_TEXT_NAV = "#FFFFFF"
COLOR_TEXT_MUTED = "#888888"
COLOR_ACCENT = "#3B82F6"
COLOR_ACCENT_HOVER = "#2563EB"
COLOR_BORDER = "#333333"
COLOR_DANGER = "#EF4444"

class YearlyReportView(ctk.CTkFrame):
    def __init__(self, master, user_id, db):
        super().__init__(master, fg_color="transparent")
        self.user_id = user_id
        self.db = db
        self.current_year = datetime.now().year
        self.income_categories = ["Wages", "Interest/dividends", "Miscellaneous"]
        
        self.pack(fill="both", expand=True)
        
        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", pady=(0, 20))
        
        self.title_lbl = ctk.CTkLabel(self.header_frame, text=f"Yearly Report - {self.current_year}", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLOR_TEXT)
        self.title_lbl.pack(side="left")
        
        self.download_btn = ctk.CTkButton(self.header_frame, text="Download PDF", font=ctk.CTkFont(weight="bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=self.download_pdf)
        self.download_btn.pack(side="right")
        
        self.year_controls = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.year_controls.pack(side="right", padx=20)
        
        self.prev_btn = ctk.CTkButton(self.year_controls, text="<", width=30, command=self.prev_year)
        self.prev_btn.pack(side="left", padx=5)
        self.next_btn = ctk.CTkButton(self.year_controls, text=">", width=30, command=self.next_year)
        self.next_btn.pack(side="left", padx=5)
        
        # Table Container (Scrollable horizontally)
        # However, CTkScrollableFrame only scrolls vertically by default.
        # We can just pack grids if it fits within the screen, or use place.
        # A 14 column grid will fit 1000px if columns are 60-70px wide.
        self.table_frame = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12, border_color=COLOR_BORDER, border_width=1)
        self.table_frame.pack(fill="both", expand=True, pady=10)
        
        self.refresh_data()
        
    def prev_year(self):
        self.current_year -= 1
        self.title_lbl.configure(text=f"Yearly Report - {self.current_year}")
        self.refresh_data()
        
    def next_year(self):
        self.current_year += 1
        self.title_lbl.configure(text=f"Yearly Report - {self.current_year}")
        self.refresh_data()
        
    def get_data(self):
        expenses_monthly = {m: 0.0 for m in range(1, 13)}
        income_monthly = {cat: {m: 0.0 for m in range(1, 13)} for cat in self.income_categories}
        
        for m in range(1, 13):
            raw = self.db.get_expenses_by_month(self.user_id, self.current_year, m)
            for _, amt, cat in raw:
                # Based on string match
                if cat in self.income_categories:
                    income_monthly[cat][m] += amt
                else:
                    expenses_monthly[m] += amt
        return expenses_monthly, income_monthly

    def refresh_data(self):
        for widget in self.table_frame.winfo_children():
            widget.destroy()
            
        expenses_monthly, income_monthly = self.get_data()
        
        months_headers = ["Category", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Year"]
        
        # Configure columns
        self.table_frame.grid_columnconfigure(0, weight=2)
        for i in range(1, 14):
            self.table_frame.grid_columnconfigure(i, weight=1)
            
        row_idx = 0
        
        # --- Expenses Section ---
        lbl = ctk.CTkLabel(self.table_frame, text="Expenses", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_DANGER)
        lbl.grid(row=row_idx, column=0, sticky="w", pady=(15, 5), padx=10)
        row_idx += 1
        
        # Headers
        for i, h in enumerate(months_headers):
            lbl = ctk.CTkLabel(self.table_frame, text=h if i>0 else "", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_DANGER)
            lbl.grid(row=row_idx, column=i, pady=5, padx=2)
        row_idx += 1
        
        def add_row(title, data_dict=None, list_data=None, is_total=False):
            nonlocal row_idx
            bg_color = COLOR_BORDER if is_total else (COLOR_BG if row_idx % 2 == 0 else "#111111")
            
            # Draw row background
            for i in range(14):
                f = ctk.CTkFrame(self.table_frame, fg_color=bg_color, corner_radius=0, height=35)
                f.grid(row=row_idx, column=i, sticky="nsew", padx=1, pady=1)
                f.grid_propagate(False)
                
                text = ""
                if i == 0:
                    text = title
                elif i < 13:
                    if data_dict:
                        text = f"₹{data_dict[i]:.2f}"
                    elif list_data:
                        text = f"₹{list_data[i-1]:.2f}"
                else:
                    if data_dict:
                        text = f"₹{sum(data_dict.values()):.2f}"
                    elif list_data:
                        text = f"₹{sum(list_data):.2f}"
                        
                align = "w" if i == 0 else "center"
                lbl = ctk.CTkLabel(self.table_frame, text=text, font=ctk.CTkFont(size=12, weight="bold" if is_total else "normal"), text_color=COLOR_TEXT)
                lbl.grid(row=row_idx, column=i, sticky="w" if i==0 else "", padx=10 if i==0 else 2, pady=5)
            row_idx += 1
            
        add_row("Total expenses", data_dict=expenses_monthly)
        
        inc_totals_by_m = {m: 0.0 for m in range(1, 13)}
        for cat in self.income_categories:
            for m in range(1, 13):
                inc_totals_by_m[m] += income_monthly[cat][m]
                
        short_extra_list = []
        for m in range(1, 13):
            short_extra_list.append(inc_totals_by_m[m] - expenses_monthly[m])
            
        add_row("Cash short/extra", list_data=short_extra_list)
        
        # --- Income Section ---
        lbl = ctk.CTkLabel(self.table_frame, text="Income", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_DANGER)
        lbl.grid(row=row_idx, column=0, sticky="w", pady=(25, 5), padx=10)
        row_idx += 1
        
        for i, h in enumerate(months_headers):
            lbl = ctk.CTkLabel(self.table_frame, text=h, font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_DANGER)
            lbl.grid(row=row_idx, column=i, pady=5, padx=2)
        row_idx += 1
        
        for cat in self.income_categories:
            add_row(cat, data_dict=income_monthly[cat])
            
        add_row("Total", data_dict=inc_totals_by_m, is_total=True)

    def download_pdf(self):
        if not HAS_FPDF:
            messagebox.showerror("Error", "FPDF Library not found. Cannot generate PDF.")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"Budget_Report_{self.current_year}.pdf",
            title="Save Yearly Report as PDF"
        )
        if not file_path:
            return
            
        try:
            self._create_pdf(file_path)
            messagebox.showinfo("Success", f"PDF successfully saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF:\n{str(e)}")
            
            
    def _create_pdf(self, output_path):
        expenses_monthly, income_monthly = self.get_data()
        
        pdf = FPDF(orientation='L', unit='mm', format='A4') 
        pdf.add_page()
        pdf.set_font("helvetica", style="B", size=16)
        pdf.cell(0, 10, f"Yearly Report - {self.current_year}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        
        months_headers = ["Category", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Year"]
        col_w_cat = 45
        col_w_month = 18
        
        def draw_row(cells, is_header=False, is_bold=False):
            pdf.set_font("helvetica", style="B" if (is_header or is_bold) else "", size=9)
            if is_header:
                pdf.set_text_color(200, 0, 0) # Reddish headers like the image
                pdf.set_fill_color(255, 255, 255)
            else:
                pdf.set_text_color(0, 0, 0)
                pdf.set_fill_color(210, 225, 240) # Light blue like the image
            
            fill = not is_header
            for idx, text in enumerate(cells):
                w = col_w_cat if idx == 0 else col_w_month
                pdf.cell(w, 8, txt=str(text), border=1, fill=fill, align="C" if idx > 0 else "L")
            pdf.ln()

        # EXPENSES SECTION
        pdf.set_font("helvetica", style="B", size=14)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 10, "Expenses", new_x="LMARGIN", new_y="NEXT")
        
        # Header
        draw_row([""] + months_headers[1:], is_header=True)
        
        # Calculate totals
        exp_row = ["Total expenses"]
        total_exp_year = 0
        for m in range(1, 13):
            val = expenses_monthly[m]
            exp_row.append(f"₹{val:,.2f}")
            total_exp_year += val
        exp_row.append(f"₹{total_exp_year:,.2f}")
        draw_row(exp_row)
        
        # Income total row (needed for cash short/extra)
        inc_totals_by_m = {m: 0.0 for m in range(1, 13)}
        for cat in self.income_categories:
            for m in range(1, 13):
                inc_totals_by_m[m] += income_monthly[cat][m]
                
        short_extra_row = ["Cash short/extra"]
        total_short_year = 0
        for m in range(1, 13):
            val = inc_totals_by_m[m] - expenses_monthly[m]
            short_extra_row.append(f"₹{val:,.2f}")
            total_short_year += val
        short_extra_row.append(f"₹{total_short_year:,.2f}")
        draw_row(short_extra_row)
        
        pdf.ln(10)
        
        # INCOME SECTION
        pdf.set_font("helvetica", style="B", size=14)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 10, "Income", new_x="LMARGIN", new_y="NEXT")
        
        draw_row(months_headers, is_header=True)
        
        year_total_income = 0
        for cat in self.income_categories:
            row = [cat]
            cat_year_total = 0
            for m in range(1, 13):
                val = income_monthly[cat][m]
                row.append(f"₹{val:,.2f}")
                cat_year_total += val
            row.append(f"₹{cat_year_total:,.2f}")
            year_total_income += cat_year_total
            draw_row(row)
            
        # Total
        total_inc_row = ["Total"]
        for m in range(1, 13):
            total_inc_row.append(f"₹{inc_totals_by_m[m]:,.2f}")
        total_inc_row.append(f"₹{year_total_income:,.2f}")
        
        # Special style for total row
        pdf.set_font("helvetica", style="B", size=9)
        pdf.set_text_color(255, 255, 255)
        pdf.set_fill_color(120, 120, 120) # Grey like the image
        for idx, text in enumerate(total_inc_row):
            w = col_w_cat if idx == 0 else col_w_month
            pdf.cell(w, 8, txt=str(text), border=1, fill=True, align="C" if idx > 0 else "L")
        pdf.ln()
