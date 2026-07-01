"""
Google Forms Auto-Submitter
============================
Submits a Google Form ~50 times with:
  - Randomized multiple-choice / checkbox answers
  - Random full names (mix-and-match first + last name pools)
  - GUI window for URL input and live progress tracking

Requirements:
    pip install selenium webdriver-manager

Usage:
    Run: python google_forms_bot.py
"""

import time
import random
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

SUBMIT_COUNT = 50
MIN_DELAY = 3
MAX_DELAY = 7
NAME_FIELD_LABEL = None  # None = fill all text inputs

# ─────────────────────────────────────────────
# NAME POOLS  (10 × 10 = 100 combos)
# ─────────────────────────────────────────────

FIRST_NAMES = [
    "Liam", "Emma", "Noah", "Olivia", "James",
    "Ava", "Lucas", "Sophia", "Ethan", "Isabella",
    "Mason", "Mia", "Elijah", "Charlotte", "Logan",
    "Amelia", "Oliver", "Harper", "Benjamin", "Evelyn",
    "Jacob", "Abigail", "Michael", "Emily", "Daniel",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Martinez", "Taylor",
    "Anderson", "Thomas", "Moore", "Jackson", "White",
    "Harris", "Clark", "Lewis", "Young", "Walker",
    "Hall", "Allen", "King", "Wright", "Scott",
]

# Non-repeating name queue: every (first, last) combo shuffled, popped one at a time.
# 25 x 25 = 625 unique combos — far more than any realistic submission count.
_name_queue: list[str] = []

def _refill_name_queue():
    global _name_queue
    combos = [f"{f} {l}" for f in FIRST_NAMES for l in LAST_NAMES]
    random.shuffle(combos)
    _name_queue = combos

def random_name() -> str:
    """Pop a unique name off the shuffled queue; refill (reshuffle) only once exhausted."""
    global _name_queue
    if not _name_queue:
        _refill_name_queue()
    return _name_queue.pop()

# ─────────────────────────────────────────────
# SELENIUM HELPERS
# ─────────────────────────────────────────────

def make_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    try:
        # Works when running as a normal Python script
        service = Service(ChromeDriverManager().install())
    except Exception:
        # Fallback for compiled exe — uses chromedriver.exe placed next to the exe
        import sys, os
        base = sys._MEIPASS if hasattr(sys, "_MEIPASS") else os.path.dirname(sys.executable)
        driver_path = os.path.join(base, "chromedriver.exe")
        service = Service(driver_path)
    return webdriver.Chrome(service=service, options=options)


def fill_and_submit(driver: webdriver.Chrome, form_url: str) -> bool:
    driver.get(form_url)
    wait = WebDriverWait(driver, 15)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='listitem']")))
    time.sleep(1)

    # ── Text / name fields ────────────────────────────────────────────────
    if NAME_FIELD_LABEL:
        for block in driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']"):
            try:
                label = block.find_element(By.CSS_SELECTOR, "span[dir='auto']").text.strip()
                if NAME_FIELD_LABEL.lower() in label.lower():
                    inp = block.find_element(By.CSS_SELECTOR, "input[type='text'], textarea")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
                    inp.clear()
                    inp.send_keys(random_name())
                    time.sleep(0.2)
                    break
            except Exception:
                continue
    else:
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea"):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
                inp.clear()
                inp.send_keys(random_name())
                time.sleep(0.2)
            except Exception:
                continue

    # ── Radio buttons ──────────────────────────────────────────────────────
    for group in driver.find_elements(By.CSS_SELECTOR, "div[role='radiogroup']"):
        options = group.find_elements(By.CSS_SELECTOR, "div[role='radio']")
        if options:
            choice = random.choice(options)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", choice)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", choice)
            time.sleep(0.3)

    # ── Checkboxes ─────────────────────────────────────────────────────────
    for group in driver.find_elements(By.CSS_SELECTOR, "div[role='group']"):
        boxes = group.find_elements(By.CSS_SELECTOR, "div[role='checkbox']")
        if not boxes:
            continue
        for box in random.sample(boxes, random.randint(1, min(3, len(boxes)))):
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", box)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", box)
            time.sleep(0.2)

    # ── Submit ─────────────────────────────────────────────────────────────
    submit_btn = wait.until(EC.presence_of_element_located(
        (By.XPATH, "//span[contains(text(),'Submit') or contains(text(),'إرسال')]/..")
    ))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", submit_btn)

    try:
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'recorded') or contains(text(),'submitted') or contains(text(),'تم')]")
        ))
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────

class BotGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pigeons Funny Google Forum Bot")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        PAD = 16
        BG      = "#1e1e2e"
        CARD    = "#2a2a3d"
        ACCENT  = "#7c3aed"
        GREEN   = "#22c55e"
        RED     = "#ef4444"
        YELLOW  = "#f59e0b"
        FG      = "#e2e8f0"
        SUBFG   = "#94a3b8"
        FONT    = ("Segoe UI", 10)
        FONT_B  = ("Segoe UI", 10, "bold")
        FONT_H  = ("Segoe UI", 13, "bold")

        self.green  = GREEN
        self.red    = RED
        self.yellow = YELLOW
        self.accent = ACCENT
        self.fg     = FG
        self.subfg  = SUBFG
        self.bg     = BG
        self.card   = CARD

        # ── Title ──────────────────────────────────────────────────────────
        tk.Label(root, text="🤖  Pigeons Funny Google Forum Bot", font=("Segoe UI", 14, "bold"),
                 bg=BG, fg=FG).pack(pady=(PAD, 4))
        tk.Label(root, text="Automates form submissions with randomized answers",
                 font=("Segoe UI", 9), bg=BG, fg=SUBFG).pack(pady=(0, PAD))

        # ── URL input card ─────────────────────────────────────────────────
        url_card = tk.Frame(root, bg=CARD, padx=PAD, pady=12)
        url_card.pack(fill="x", padx=PAD, pady=(0, 10))

        tk.Label(url_card, text="Form URL", font=FONT_B, bg=CARD, fg=FG).pack(anchor="w")
        tk.Label(url_card, text="Paste your Google Form viewform link",
                 font=("Segoe UI", 8), bg=CARD, fg=SUBFG).pack(anchor="w", pady=(0, 6))

        self.url_var = tk.StringVar()
        url_entry = tk.Entry(url_card, textvariable=self.url_var, font=FONT,
                             bg="#13131f", fg=FG, insertbackground=FG,
                             relief="flat", bd=6, width=52)
        url_entry.pack(fill="x")

        # ── Submissions count ──────────────────────────────────────────────
        count_card = tk.Frame(root, bg=CARD, padx=PAD, pady=12)
        count_card.pack(fill="x", padx=PAD, pady=(0, 10))

        tk.Label(count_card, text="Number of Submissions", font=FONT_B,
                 bg=CARD, fg=FG).pack(anchor="w")

        self.count_var = tk.IntVar(value=SUBMIT_COUNT)
        count_spin = tk.Spinbox(count_card, from_=1, to=500, textvariable=self.count_var,
                                font=FONT, bg="#13131f", fg=FG, insertbackground=FG,
                                buttonbackground=CARD, relief="flat", bd=6, width=8)
        count_spin.pack(anchor="w", pady=(6, 0))

        # ── Progress card ──────────────────────────────────────────────────
        prog_card = tk.Frame(root, bg=CARD, padx=PAD, pady=12)
        prog_card.pack(fill="x", padx=PAD, pady=(0, 10))

        # Stats row
        stats_row = tk.Frame(prog_card, bg=CARD)
        stats_row.pack(fill="x", pady=(0, 8))

        self._stat(stats_row, "Submitted",  "0", GREEN,  0)
        self._stat(stats_row, "Failed",     "0", RED,    1)
        self._stat(stats_row, "Remaining",  str(SUBMIT_COUNT), SUBFG, 2)
        self._stat(stats_row, "Progress",   "0%", ACCENT, 3)

        # Progress bar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Bot.Horizontal.TProgressbar",
                        troughcolor="#13131f", background=ACCENT,
                        bordercolor=CARD, lightcolor=ACCENT, darkcolor=ACCENT)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_card, variable=self.progress_var,
                                            maximum=100, length=460,
                                            style="Bot.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x")

        # Status label
        self.status_var = tk.StringVar(value="Ready — paste a URL and click Start")
        tk.Label(prog_card, textvariable=self.status_var, font=("Segoe UI", 9),
                 bg=CARD, fg=SUBFG).pack(anchor="w", pady=(6, 0))

        # ── Log box ────────────────────────────────────────────────────────
        log_card = tk.Frame(root, bg=CARD, padx=PAD, pady=10)
        log_card.pack(fill="both", expand=True, padx=PAD, pady=(0, 10))

        tk.Label(log_card, text="Log", font=FONT_B, bg=CARD, fg=FG).pack(anchor="w")

        log_frame = tk.Frame(log_card, bg=CARD)
        log_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.log_box = tk.Text(log_frame, height=10, font=("Consolas", 9),
                               bg="#13131f", fg=FG, relief="flat",
                               state="disabled", wrap="word")
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview, bg=CARD)
        self.log_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)

        # Tag colors for log
        self.log_box.tag_config("ok",   foreground=GREEN)
        self.log_box.tag_config("fail", foreground=RED)
        self.log_box.tag_config("warn", foreground=YELLOW)
        self.log_box.tag_config("info", foreground=SUBFG)
        self.log_box.tag_config("head", foreground=ACCENT)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = tk.Frame(root, bg=BG)
        btn_row.pack(pady=(0, PAD))

        self.start_btn = tk.Button(btn_row, text="▶  Start", font=FONT_B,
                                   bg=ACCENT, fg="white", relief="flat",
                                   padx=24, pady=8, cursor="hand2",
                                   command=self.start)
        self.start_btn.pack(side="left", padx=6)

        self.stop_btn = tk.Button(btn_row, text="■  Stop", font=FONT_B,
                                  bg="#374151", fg=SUBFG, relief="flat",
                                  padx=24, pady=8, cursor="hand2",
                                  command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        # State
        self._running   = False
        self._successes = 0
        self._failures  = 0
        self._total     = 0

    # ── helper: stat box ───────────────────────────────────────────────────
    def _stat(self, parent, label, value, color, col):
        frame = tk.Frame(parent, bg=self.card, padx=10)
        frame.grid(row=0, column=col, sticky="w", padx=(0, 20))
        var = tk.StringVar(value=value)
        tk.Label(frame, textvariable=var, font=("Segoe UI", 18, "bold"),
                 bg=self.card, fg=color).pack(anchor="w")
        tk.Label(frame, text=label, font=("Segoe UI", 8),
                 bg=self.card, fg=self.subfg).pack(anchor="w")
        setattr(self, f"_{label.lower()}_var", var)

    # ── logging ────────────────────────────────────────────────────────────
    def log(self, msg, tag="info"):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n", tag)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _do)

    # ── update stats ───────────────────────────────────────────────────────
    def _update_stats(self):
        done = self._successes + self._failures
        pct  = int(done / self._total * 100) if self._total else 0
        rem  = self._total - done

        self.root.after(0, lambda: [
            self._submitted_var.set(str(self._successes)),
            self._failed_var.set(str(self._failures)),
            self._remaining_var.set(str(rem)),
            self._progress_var.set(f"{pct}%"),
            self.progress_var.set(pct),
        ])

    # ── start ──────────────────────────────────────────────────────────────
    def start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Please paste a Google Form URL first.")
            return
        if "docs.google.com/forms" not in url:
            messagebox.showerror("Invalid URL", "That doesn't look like a Google Forms link.")
            return

        self._total     = self.count_var.get()
        self._successes = 0
        self._failures  = 0
        self._running   = True
        _refill_name_queue()

        self._submitted_var.set("0")
        self._failed_var.set("0")
        self._remaining_var.set(str(self._total))
        self._progress_var.set("0%")
        self.progress_var.set(0)

        self.start_btn.configure(state="disabled", bg="#4b2e9e")
        self.stop_btn.configure(state="normal", bg="#ef4444", fg="white")
        self.status_var.set("Starting bot…")

        self.log(f"━━ Starting {self._total} submissions ━━", "head")
        self.log(f"URL: {url}", "info")

        threading.Thread(target=self._run, args=(url,), daemon=True).start()

    # ── stop ───────────────────────────────────────────────────────────────
    def stop(self):
        self._running = False
        self.status_var.set("Stopping after current submission…")
        self.log("⚠ Stop requested by user", "warn")

    # ── bot thread ─────────────────────────────────────────────────────────
    def _run(self, url: str):
        driver = None
        try:
            self.root.after(0, lambda: self.status_var.set("Launching Chrome…"))
            self.log("Launching headless Chrome…", "info")
            try:
                driver = make_driver()
                self.log("✅ Chrome launched successfully", "ok")
            except Exception as chrome_err:
                self.log(f"❌ Chrome failed to launch: {chrome_err}", "fail")
                self.root.after(0, lambda: [
                    self.start_btn.configure(state="normal", bg=self.accent),
                    self.stop_btn.configure(state="disabled", bg="#374151", fg=self.subfg),
                    self.status_var.set("Failed — Chrome could not launch"),
                ])
                return

            for i in range(1, self._total + 1):
                if not self._running:
                    break

                self.root.after(0, lambda i=i: self.status_var.set(
                    f"Submitting {i} of {self._total}…"))
                self.log(f"[{i}/{self._total}] Submitting…", "info")

                try:
                    ok = fill_and_submit(driver, url)
                    if ok:
                        self._successes += 1
                        self.log(f"[{i}/{self._total}] ✅ Success", "ok")
                    else:
                        self._failures += 1
                        self.log(f"[{i}/{self._total}] ⚠ Not confirmed", "warn")
                except Exception as e:
                    self._failures += 1
                    self.log(f"[{i}/{self._total}] ❌ Error: {e}", "fail")

                self._update_stats()

                if i < self._total and self._running:
                    delay = random.uniform(MIN_DELAY, MAX_DELAY)
                    self.root.after(0, lambda d=delay: self.status_var.set(
                        f"Waiting {d:.1f}s before next submission…"))
                    time.sleep(delay)

        finally:
            if driver:
                driver.quit()

            total_done = self._successes + self._failures
            self.log(
                f"━━ Done: {self._successes} succeeded, "
                f"{self._failures} failed out of {total_done} attempts ━━", "head")

            self.root.after(0, lambda: [
                self.start_btn.configure(state="normal", bg=self.accent),
                self.stop_btn.configure(state="disabled", bg="#374151", fg=self.subfg),
                self.status_var.set(
                    f"Finished — {self._successes}/{total_done} submissions confirmed"),
                self.progress_var.set(100 if self._running else self.progress_var.get()),
            ])
            self._running = False


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.configure(bg="#1e1e2e")
    app = BotGUI(root)
    root.mainloop()
