import customtkinter as ctk

app = ctk.CTk()
app.geometry("400x400")

def open_modal():
    modal = ctk.CTkFrame(app, width=200, height=200, fg_color="red")
    modal.place(relx=0.5, rely=0.5, anchor="center")
    
    close_btn = ctk.CTkButton(modal, text="Close", command=lambda: [modal.grab_release(), modal.destroy()])
    close_btn.pack(pady=50)
    
    # Grab all events to this modal frame
    modal.grab_set()

btn = ctk.CTkButton(app, text="Open Modal", command=open_modal)
btn.pack(pady=50)

def bg_clicked():
    print("Background clicked!")

button2 = ctk.CTkButton(app, text="Test Background", command=bg_clicked)
button2.pack(pady=10)

app.after(1000, lambda: app.destroy())
app.mainloop()
