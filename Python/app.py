import tkinter as tk
from tkinter import font as tkfont
import serial
import threading
import time
import os
from datetime import datetime
from PIL import Image, ImageTk


# --- KONFIGURATION & DESIGN ---
SERIAL_PORT = 'COM8'
BAUD_RATE = 57600
BG_COLOR = "#f4f8fd"  
ADI_BLUE = "#005a87"


# --- SYSTEMVARIABLER ---
ser = None
system_power_on = False
is_running = False
is_paused = False
log_box = None
monitor_win = None
start_height = 0.0 # Sparar bas-höjden vid start
hourly_data=[]

# Försök ansluta till serieporten direkt
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    print(f"Ansluten till {SERIAL_PORT}")
except Exception as e:
    print(f"Serie-fel vid start: {e}")


# --- SKAPA HUVUDFÖNSTRET ---
root = tk.Tk()
root.title("VGuard Control System")
root.geometry("480x720")
root.configure(bg="white")

# --- BILDHANTERING (Säker laddning) ---
base_path = os.path.dirname(os.path.abspath(__file__))


def load_icon(filename, size, rotate=0):
    try:
        path = os.path.join(base_path, filename)
        img = Image.open(path).convert("RGBA")
        if rotate:
            img = img.rotate(rotate, expand=True)
        img = img.resize(size, Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"Kunde inte ladda {filename}: {e}")
        return None

# Spara bilderna i root för att förhindra "garbage collection"
root.img_play = load_icon("play.png", (50, 50), rotate=-90)
root.img_power = load_icon("on.png", (45, 45))


# --- FUNKTIONER ---
def read_from_arduino():
    """Bakgrundstråd som tolkar Arduinons reglerdata."""
    global log_box, start_height
    while True:
        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    raw_line = ser.readline().decode('utf-8', errors='ignore').strip()
                    
                    if raw_line and log_box and tk.Text.winfo_exists(log_box):
                        now_time = datetime.now().strftime("%H:%M:%S")
                        
                        if "|" in raw_line:
                            try:
                                # Dela upp formatet: T:1|Mal:0.63|Nu:0.41|Tryck:0.9|Status:OK
                                # Inuti if "|" in raw_line:
                                p = raw_line.split("|")
                                t_str = p[0].split(":")[1].strip()
                                nu_val = float(p[2].split(":")[1])

                                if t_str != "0": # Vi sparar bara faktiska timmar
                                    prev_total = hourly_data[-1][1] if hourly_data else 0
                                    current_total = prev_total + nu_val
                                    hourly_data.append((nu_val, current_total))
                                    
                                   


                                t_val  = p[0].split(":")[1].strip() if ":" in p[0] else p[0]
                                sp_val = p[1].split(":")[1].strip() if ":" in p[1] else p[1]
                                pv_val = p[2].split(":")[1].strip() if ":" in p[2] else p[2]
                                
                                # Beräkna relativ höjd: Bas + förändring från Arduino
                                try:
                                    diff = float(p[3].split(":")[1].strip())
                                    current_h = start_height + diff
                                    pr_display = f"{current_h:.1f}"
                                except:
                                    pr_display = p[3].split(":")[1].strip()

                                st_val = p[4].split(":")[1].strip() if ":" in p[4] else p[4]
                                
                                out = f"{now_time:<15}{t_val:<15}{sp_val + ' ml/h':<20}{pv_val + ' ml/h':<25}{pr_display:<20}{st_val}\n"
                                log_box.insert(tk.END, out)

                                # Om Arduinon når timme 24, trigga rapporten
                                if t_str == "24":
                                    generate_final_report(current_total)
                            except:
                                log_box.insert(tk.END, f"{now_time:<15} DATA: {raw_line}\n")
                        else:
                            log_box.insert(tk.END, f"{now_time:<15} SYS: {raw_line}\n")
                        
                        log_box.see(tk.END)
            except:
                pass
        time.sleep(0.05)


def open_monitor_window():
    global log_box, monitor_win, start_height
    if monitor_win is not None and monitor_win.winfo_exists():
        return
    
    # Låser startvärdet från GUI när vi öppnar monitorn
    try:
        start_height = float(entry_pos.get())
    except:
        start_height = 10.0
   
    monitor_win = tk.Toplevel(root)
    monitor_win.title("VGuard Live Monitoring")
    monitor_win.geometry("1100x500")
    monitor_win.configure(bg=BG_COLOR)


    tk.Label(monitor_win, text="LIVE MONITORING", font=("Helvetica", 14, "bold"),
              bg=ADI_BLUE, fg="white", pady=10).pack(fill="x")


    content = tk.Frame(monitor_win, bg=BG_COLOR, padx=20, pady=10)
    content.pack(expand=True, fill="both")


    header = f"{'REALTID':<18}{'TID (H)':<17}{'SETPOINT (SP)':<22}{'PROCESS VARIABLE (PV)':<28}{'HÖJDÄNDRING(mmHg)':<23}{'STATUS'}"
    tk.Label(content, text=header, font=("Courier", 10, "bold"), bg=BG_COLOR, fg="#333", anchor="w").pack(fill="x")


    log_box = tk.Text(content, font=("Courier", 11), bg="white", fg="black", bd=1, relief="solid", padx=10, pady=10)
    log_box.pack(expand=True, fill="both", pady=5)


    now = datetime.now().strftime("%H:%M:%S")
    # Skriver ut startvärdet vid tiden 0
  

def generate_final_report(final_total):
    goal = float(entry_goal.get())
    diff = ((final_total - goal) / goal) * 100
    
    log_box.insert(tk.END, "\n" + "="*50 + "\n")
    log_box.insert(tk.END, "       --- DYGNSSUMMERING T1-T24 ---\n")
    log_box.insert(tk.END, "="*50 + "\n")
    for i, data in enumerate(hourly_data):
        log_box.insert(tk.END, f"T{i+1:<2}: {data[0]:>6.2f} ml  (Ackumulerat: {data[1]:>6.2f} ml)\n")
    log_box.insert(tk.END, "-"*50 + "\n")
    log_box.insert(tk.END, f"Målvolym:      {goal:.2f} ml\n")
    log_box.insert(tk.END, f"Faktisk volym: {final_total:.2f} ml\n")
    log_box.insert(tk.END, f"Total avvikelse: {diff:+.2f}%\n")
    log_box.insert(tk.END, "="*50 + "\n")


def toggle_system_power():
    global system_power_on, is_running, is_paused, monitor_win
    if not system_power_on:
        system_power_on = True
        on_canvas.itemconfig(on_lamp_circle, fill="#32CD32")
    else:
        system_power_on = False
        is_running = False
        is_paused = False
        on_canvas.itemconfig(on_lamp_circle, fill="white")
        active_led.itemconfig(led_circle, fill="white")    
        if ser: ser.write(b"STOP\n")
        if monitor_win is not None and monitor_win.winfo_exists():
            monitor_win.destroy()


def adjust_goal(delta):
    try:
        val = float(entry_goal.get())
        entry_goal.delete(0, tk.END)
        entry_goal.insert(0, f"{max(0.0, val + delta):.1f}")
    except:
        entry_goal.insert(0, "250.0")

def adjust_pos(delta):
    try:
        val = float(entry_pos.get())
        entry_pos.delete(0, tk.END)
        entry_pos.insert(0, f"{max(0.0, val + delta):.1f}")
    except:
        entry_pos.insert(0, "10.0")

def toggle_treatment():
    global is_running, is_paused
    if not system_power_on: return
    if not ser: return


    if not is_running:
        # Skickar Mål och det valda startvärdet för höjd
        ser.write(f"START:{entry_goal.get()}:{entry_pos.get()}\n".encode())
        is_running = True
        is_paused = False
        active_led.itemconfig(led_circle, fill="#32CD32")
        open_monitor_window()
    else:
        if not is_paused:
            ser.write(b"PAUSE\n")
            is_paused = True
            active_led.itemconfig(led_circle, fill="#ffd700")
        else:
            ser.write(b"RESUME\n")
            is_paused = False
            active_led.itemconfig(led_circle, fill="#32CD32")


# --- GUI DESIGN ---
main = tk.Frame(root, bg=BG_COLOR, bd=1, relief="ridge", padx=20, pady=20)
main.place(relx=0.5, rely=0.5, anchor="center", width=440, height=660)


header_frame = tk.Frame(main, bg=BG_COLOR)
header_frame.pack(fill="x", pady=(0, 30))
# Skapa en Text-widget istället för en Label
logo_text = tk.Text(
    header_frame, 
    font=("Helvetica", 35, "bold"), 
    bg=BG_COLOR, 
    bd=0,                 # Tar bort ramen runt textrutan
    highlightthickness=0, # Tar bort fokus-ramen
    height=1,             # Sätter höjden till exakt en rad
    width=4               # Sätter bredden så den precis passar "ADI"
)
logo_text.pack(side="left")

# Skapa färg-taggar
logo_text.tag_config("dark", foreground="#2c3e50")
logo_text.tag_config("green", foreground="#27ae60")

# Skriv ut bokstäverna med rätt färg direkt efter varandra
logo_text.insert("insert", "AD", "dark")
logo_text.insert("insert", "i", "green")

# Gör textrutan "read-only" så att användaren inte kan råka radera loggan
logo_text.config(state="disabled")

on_group = tk.Frame(header_frame, bg=BG_COLOR)
on_group.pack(side="right")
top_status = tk.Frame(on_group, bg=BG_COLOR)
top_status.pack(anchor="e")
tk.Label(top_status, text="Automatic Drainage", font=("Helvetica", 9), bg=BG_COLOR).pack(side="left")
on_canvas = tk.Canvas(top_status, width=20, height=20, bg=BG_COLOR, highlightthickness=0)
on_lamp_circle = on_canvas.create_oval(4, 4, 16, 16, fill="white", outline="#999")
on_canvas.pack(side="left", padx=5)
tk.Label(top_status, text="ON", font=("Helvetica", 9, "bold"), bg=BG_COLOR).pack(side="left")


btn_power = tk.Button(on_group, command=toggle_system_power, bg=BG_COLOR, activebackground=BG_COLOR, bd=0)
if root.img_power: btn_power.config(image=root.img_power)
btn_power.pack(pady=(5, 0), anchor="e")

tk.Label(main, text="Target (ml/24h)", font=("Helvetica", 12, "bold"), bg=BG_COLOR).pack(anchor="w", pady=(10, 0))
display_frame = tk.Frame(main, bg=BG_COLOR, pady=10)
display_frame.pack(fill="x")
disp_container = tk.Frame(display_frame, bg="#e0e0e0", padx=15, pady=10, bd=1, relief="sunken")
disp_container.pack(side="left")
entry_goal = tk.Entry(disp_container, font=("Courier", 30, "bold"), justify="center", width=5, bg="#e0e0e0", bd=0)
entry_goal.insert(0, "250.0")
entry_goal.pack()


btn_f = tk.Frame(display_frame, bg=BG_COLOR)
btn_f.pack(side="left", padx=25)
for txt, d in [("−", -10), ("+", 10)]:
    tk.Button(btn_f, text=txt, command=lambda delta=d: adjust_goal(delta),
              font=("Arial", 18, "bold"), width=2, bg="white", fg=ADI_BLUE, bd=2, relief="solid").pack(side="left", padx=1)


# --- CURRENT POSITION SECTION ---
tk.Label(main, text="Current Position (mmHg)", font=("Helvetica", 12, "bold"), bg=BG_COLOR).pack(anchor="w", pady=(20, 0))
pos_frame = tk.Frame(main, bg=BG_COLOR, pady=5)
pos_frame.pack(fill="x")
pos_container = tk.Frame(pos_frame, bg="#e0e0e0", padx=15, pady=10, bd=1, relief="sunken")
pos_container.pack(side="left")
entry_pos = tk.Entry(pos_container, font=("Courier", 30, "bold"), justify="center", width=5, bg="#e0e0e0", bd=0)
entry_pos.insert(0, "10.0")
entry_pos.pack()


btn_pos_f = tk.Frame(pos_frame, bg=BG_COLOR)
btn_pos_f.pack(side="left", padx=25)
for txt, d in [("−", -1), ("+", 1)]: # Justerat till steg om 1 mmHg
    tk.Button(btn_pos_f, text=txt, command=lambda delta=d: adjust_pos(delta),
              font=("Arial", 18, "bold"), width=2, bg="white", fg=ADI_BLUE, bd=2, relief="solid").pack(side="left", padx=1)



treatment_frame = tk.Frame(main, bg=BG_COLOR, pady=30)
treatment_frame.pack(fill="x")
tk.Label(treatment_frame, text="Treatment", font=("Helvetica", 12, "bold"), bg=BG_COLOR).pack(anchor="w")
controls_row = tk.Frame(treatment_frame, bg=BG_COLOR)
controls_row.pack(fill="x", pady=10)
active_group = tk.Frame(controls_row, bg=BG_COLOR)
active_group.pack(side="left")
active_led = tk.Canvas(active_group, width=24, height=24, bg=BG_COLOR, highlightthickness=0)
led_circle = active_led.create_oval(4, 4, 20, 20, fill="white", outline="#999")
active_led.pack(side="left")
tk.Label(active_group, text="Active", font=("Helvetica", 11), bg=BG_COLOR).pack(side="left", padx=8)


btn_start = tk.Button(controls_row, command=toggle_treatment, bg="white", bd=2, relief="solid")
if root.img_play: btn_start.config(image=root.img_play)
btn_start.pack(side="left", expand=True, padx=(0, 70))


threading.Thread(target=read_from_arduino, daemon=True).start()
root.mainloop()