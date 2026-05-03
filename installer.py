"""
Lethal Company Repack Installer
Author: Duckey
"""
import urllib.request
import ssl
import certifi

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.request
import zipfile
import shutil
import tempfile
import threading
import time
from pathlib import Path

# COM support for winshell
import pythoncom
import winshell
import sys
import os

# ---------- Fix SSL certificate verification ----------
ssl_context = ssl.create_default_context(cafile=certifi.where())
https_handler = urllib.request.HTTPSHandler(context=ssl_context)
opener = urllib.request.build_opener(https_handler)
urllib.request.install_opener(opener)
# ----------------------------------------------------

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        # running as exe -> files are in _MEIPASS temp folder
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Inside ModernInstaller.__init__, after root is created:

# ---------- Config ----------
GAME_URL = "https://github.com/Duckey86/lethalCompanyDownloadV80/releases/download/Release1/DuckeyLethal.zip"
APP_NAME = "Lethal Company"
SHORTCUT_NAME = "Lethal Company (M4CKD0GE Repack).lnk"
# ---------------------------

class ModernInstaller:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} Installer")
        root.geometry("580x380")
        root.resizable(False, False)
        root.configure(bg="#f0f0f0")
        self.root.iconbitmap(resource_path("installer.ico"))

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#f0f0f0", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", font=("Segoe UI", 10))
        style.configure("Green.TButton", foreground="white", background="#4CAF50", font=("Segoe UI", 11, "bold"))
        style.map("Green.TButton", background=[("active", "#45a049")])
        style.configure("Red.TButton", foreground="white", background="#f44336", font=("Segoe UI", 11, "bold"))
        style.map("Red.TButton", background=[("active", "#d32f2f")])
        style.configure("TProgressbar", thickness=12, background="#4CAF50")

        # Header
        header = tk.Frame(root, bg="#2c3e50", height=60)
        header.pack(fill=tk.X)
        tk.Label(header, text=f"{APP_NAME} Installer", fg="white", bg="#2c3e50",
                 font=("Segoe UI", 14, "bold")).pack(pady=15)

        # Main content frame
        main = tk.Frame(root, bg="#f0f0f0")
        main.pack(padx=30, pady=20, fill=tk.BOTH, expand=True)

        # Folder selection
        tk.Label(main, text="Installation folder:", font=("Segoe UI", 11, "bold"), bg="#f0f0f0").pack(anchor=tk.W)
        dir_frame = tk.Frame(main, bg="#f0f0f0")
        dir_frame.pack(fill=tk.X, pady=(5, 15))
        self.dir_var = tk.StringVar(value=os.path.join("C:\\", "Games", APP_NAME))
        tk.Entry(dir_frame, textvariable=self.dir_var, font=("Segoe UI", 10), width=50).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(dir_frame, text="Browse", command=self.browse).pack(side=tk.LEFT, padx=(10, 0))

        # Progress area
        progress_frame = tk.Frame(main, bg="#f0f0f0")
        progress_frame.pack(fill=tk.X, pady=10)

        # Custom progress bar on canvas
        self.progress_canvas = tk.Canvas(progress_frame, height=12, bg="#f0f0f0", bd=0, highlightthickness=0)
        self.progress_canvas.pack(fill=tk.X)

        # Stats row (percentage, speed, ETA)
        stats_frame = tk.Frame(progress_frame, bg="#f0f0f0")
        stats_frame.pack(fill=tk.X, pady=5)
        self.pct_label = tk.Label(stats_frame, text="0%", font=("Segoe UI", 16, "bold"), fg="#2c3e50", bg="#f0f0f0")
        self.pct_label.pack(side=tk.LEFT)
        self.speed_label = tk.Label(stats_frame, text="0 MB/s", font=("Segoe UI", 10), fg="#7f8c8d", bg="#f0f0f0")
        self.speed_label.pack(side=tk.LEFT, padx=20)
        self.eta_label = tk.Label(stats_frame, text="--:--", font=("Segoe UI", 10), fg="#7f8c8d", bg="#f0f0f0")
        self.eta_label.pack(side=tk.RIGHT)

        # Status label
        self.status_label = tk.Label(main, text="Ready", font=("Segoe UI", 10, "italic"), fg="#95a5a6", bg="#f0f0f0")
        self.status_label.pack(anchor=tk.W, pady=(5, 15))

        # Buttons
        btn_frame = tk.Frame(main, bg="#f0f0f0")
        btn_frame.pack()
        self.install_btn = ttk.Button(btn_frame, text="Install", style="Green.TButton", command=self.start_install, width=14)
        self.install_btn.pack(side=tk.LEFT, padx=10)
        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", style="Red.TButton", command=self.cancel, state=tk.DISABLED, width=14)
        self.cancel_btn.pack(side=tk.LEFT, padx=10)

        # Thread control
        self.cancel_flag = False
        self.start_time = None

    def browse(self):
        folder = filedialog.askdirectory(initialdir=self.dir_var.get())
        if folder:
            self.dir_var.set(folder)

    # ---------- UI update helpers ----------
    def update_status(self, msg):
        self.status_label.config(text=msg)

    def reset_progress(self):
        self.progress_canvas.delete("all")
        self.pct_label.config(text="0%")
        self.speed_label.config(text="0 MB/s")
        self.eta_label.config(text="--:--")

    def set_progress_percent(self, percent):
        """Redraw the green progress bar and update the big percentage."""
        self.progress_canvas.delete("all")
        width = self.progress_canvas.winfo_width()
        if width > 1:
            fill_width = (percent / 100) * width
            self.progress_canvas.create_rectangle(0, 0, fill_width, 12, fill="#4CAF50", outline="")
        self.pct_label.config(text=f"{percent}%")

    def update_stats(self, speed_mb, eta_str):
        self.speed_label.config(text=f"{speed_mb:.1f} MB/s")
        self.eta_label.config(text=eta_str)

    def cancel(self):
        self.cancel_flag = True
        self.update_status("Cancelling...")

    # ---------- Installation workflow ----------
    def start_install(self):
        self.install_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.cancel_flag = False
        self.reset_progress()
        threading.Thread(target=self.install_thread, daemon=True).start()

    def install_thread(self):
        # Initialize COM for this thread (needed for winshell)
        pythoncom.CoInitialize()
        try:
            dest_str = self.dir_var.get()
            dest = Path(dest_str)

            # Clean / create destination
            self.root.after(0, self.update_status, "Preparing destination folder...")
            if dest.exists():
                shutil.rmtree(str(dest))
            dest.mkdir(parents=True, exist_ok=True)

            # Download
            zip_path_str = os.path.join(tempfile.gettempdir(), "game.zip")
            self.root.after(0, self.update_status, "Downloading game files...")
            self.start_time = time.time()

            # Progress hook
            def progress_hook(count, block_size, total_size):
                if self.cancel_flag:
                    raise Exception("Download cancelled by user.")
                if total_size > 0:
                    downloaded = count * block_size
                    percent = min(int(downloaded * 100 / total_size), 100)

                    elapsed = time.time() - self.start_time
                    if elapsed > 0:
                        speed = downloaded / elapsed   # bytes/sec
                        speed_mb = speed / (1024 * 1024)
                        if speed > 0:
                            remaining_bytes = total_size - downloaded
                            eta_seconds = remaining_bytes / speed
                            eta_min = int(eta_seconds // 60)
                            eta_sec = int(eta_seconds % 60)
                            eta_str = f"{eta_min:02d}:{eta_sec:02d}"
                        else:
                            eta_str = "--:--"
                    else:
                        speed_mb = 0
                        eta_str = "--:--"

                    self.root.after(0, self.set_progress_percent, percent)
                    self.root.after(0, self.update_stats, speed_mb, eta_str)
                    self.root.after(0, self.update_status, f"Downloading... {percent}%")

            request = urllib.request.Request(
                GAME_URL,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            urllib.request.urlretrieve(GAME_URL, zip_path_str, reporthook=progress_hook)

            if self.cancel_flag:
                self.root.after(0, messagebox.showinfo, "Cancelled", "Installation cancelled.")
                return

            # Extraction
            self.root.after(0, self.update_status, "Extracting game files...")
            self.root.after(0, self.reset_progress)
            with zipfile.ZipFile(zip_path_str, 'r') as zf:
                zf.extractall(str(dest))
            os.remove(zip_path_str)

            # Flatten "Lethal Company" folder
            game_subfolder = dest / APP_NAME
            if game_subfolder.exists() and game_subfolder.is_dir():
                self.root.after(0, self.update_status, "Finishing installation...")
                for item in game_subfolder.iterdir():
                    shutil.move(str(item), str(dest / item.name))
                shutil.rmtree(str(game_subfolder))

            # Desktop shortcut (now COM is initialized)
            desktop = Path(winshell.desktop())
            shortcut = desktop / SHORTCUT_NAME
            exe_path = dest / f"{APP_NAME}.exe"
            if exe_path.exists():
                with winshell.shortcut(str(shortcut)) as link:
                    link.path = str(exe_path)
                    link.working_directory = str(dest)
                    link.description = f"{APP_NAME} (M4CKD0GE Repack)"

            self.root.after(0, self.update_status, "Installation complete!")
            self.root.after(0, messagebox.showinfo, "Success", "Lethal Company has been installed successfully!")

        except Exception as e:
            if not self.cancel_flag:
                self.root.after(0, messagebox.showerror, "Error", str(e))
        finally:
            pythoncom.CoUninitialize()
            self.root.after(0, lambda: self.install_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.cancel_btn.config(state=tk.DISABLED))

# ---------- Main ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = ModernInstaller(root)
    root.mainloop()