"""
Pigeons Funny Google Forum Bot
================================
Submits a Google Form multiple times with randomized answers.
Supports: text, multiple choice, checkboxes, dropdowns, linear scale, date/time, email.
Works in any language/region. Accepts full and shortened Google Form links.

Requirements:
    pip install selenium webdriver-manager requests pystray Pillow
"""

import time
import random
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import json
import os
import math
import requests

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

# Suppress webdriver-manager console/download window before anything else
import os as _os
_os.environ["WDM_LOG"]              = "0"
_os.environ["WDM_LOG_LEVEL"]        = "0"
_os.environ["WDM_PRINT_FIRST_LINE"] = "False"
_os.environ["WDM_LOCAL"]            = "1"   # cache driver locally, skip re-download noise

SUBMIT_COUNT  = 50
MAX_RETRIES   = 3
DEBUG_VISIBLE = False  # ← Set True to watch Chrome live; False for headless
CONFIG_FILE   = os.path.join(os.path.expanduser("~"), ".pgfb_config.json")
LOG_FILE      = os.path.join(os.path.expanduser("~"), ".pgfb_history.json")

SPEED_PRESETS = {
    "Slow":   (6, 12),
    "Normal": (3, 7),
    "Fast":   (1, 3),
}

CHART_COLORS = [
    "#7c3aed", "#22c55e", "#ef4444", "#f59e0b", "#3b82f6",
    "#ec4899", "#14b8a6", "#f97316", "#8b5cf6", "#06b6d4",
]

# ─────────────────────────────────────────────
# THEMES
# ─────────────────────────────────────────────

THEMES = {
    "Dark": {
        "bg":     "#1e1e2e",
        "card":   "#2a2a3d",
        "input":  "#13131f",
        "fg":     "#e2e8f0",
        "subfg":  "#94a3b8",
        "accent": "#7c3aed",
        "green":  "#22c55e",
        "red":    "#ef4444",
        "yellow": "#f59e0b",
    },
    "Light": {
        "bg":     "#f1f5f9",
        "card":   "#ffffff",
        "input":  "#e2e8f0",
        "fg":     "#0f172a",
        "subfg":  "#64748b",
        "accent": "#7c3aed",
        "green":  "#16a34a",
        "red":    "#dc2626",
        "yellow": "#d97706",
    },
}

# ─────────────────────────────────────────────
# NAME & EMAIL POOLS
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

EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]

_name_queue: list = []
_current_name: str = ""

def _refill_name_queue():
    global _name_queue
    combos = [f"{f} {l}" for f in FIRST_NAMES for l in LAST_NAMES]
    random.shuffle(combos)
    _name_queue = combos

def random_name() -> str:
    global _name_queue, _current_name
    if not _name_queue:
        _refill_name_queue()
    _current_name = _name_queue.pop()
    return _current_name

def random_email(name: str = "") -> str:
    """Generate a realistic email matched to the current name."""
    if not name:
        name = _current_name or "user"
    parts = name.lower().split()
    if len(parts) >= 2:
        style = random.choice([
            f"{parts[0]}.{parts[1]}",
            f"{parts[0]}{parts[1]}",
            f"{parts[0]}.{parts[1]}{random.randint(10,99)}",
            f"{parts[0][0]}{parts[1]}",
            f"{parts[0]}{random.randint(1,999)}",
        ])
    else:
        style = f"{parts[0]}{random.randint(1,999)}"
    return f"{style}@{random.choice(EMAIL_DOMAINS)}"

def random_date() -> str:
    start = datetime(1990, 1, 1)
    end   = datetime(2005, 12, 31)
    delta = end - start
    return (start + timedelta(days=random.randint(0, delta.days))).strftime("%m/%d/%Y")

def random_time() -> str:
    return f"{random.randint(8,20):02d}:{random.choice([0,15,30,45]):02d}"

# ─────────────────────────────────────────────
# URL HELPERS
# ─────────────────────────────────────────────

def resolve_url(url: str) -> str:
    url = url.strip()
    if "forms.gle" in url or "goo.gl" in url:
        try:
            r = requests.get(url, allow_redirects=True, timeout=10)
            url = r.url
        except Exception:
            pass
    if "viewform" not in url and "formResponse" not in url:
        url = url.rstrip("/") + "/viewform"
    return url

# ─────────────────────────────────────────────
# CONFIG & HISTORY
# ─────────────────────────────────────────────

def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data: dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def append_history(url: str, total: int, succeeded: int, failed: int):
    try:
        history = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f:
                history = json.load(f)
        history.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "url": url,
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
        })
        with open(LOG_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass

# ─────────────────────────────────────────────
# BIAS
# ─────────────────────────────────────────────

def biased_choice(options: list, bias: float):
    n = len(options)
    if n == 1:
        return options[0]
    weights = []
    for i in range(n):
        pos = i / (n - 1) if n > 1 else 0.5
        if bias < 0:
            w = 1.0 + abs(bias) * 4 * (1.0 - pos)
        elif bias > 0:
            w = 1.0 + bias * 4 * pos
        else:
            w = 1.0
        weights.append(max(w, 0.01))
    return random.choices(options, weights=weights, k=1)[0]

# ─────────────────────────────────────────────
# SELENIUM
# ─────────────────────────────────────────────

def make_driver() -> webdriver.Chrome:
    import subprocess
    options = webdriver.ChromeOptions()

    if not DEBUG_VISIBLE:
        # Auto-detect Chrome version and use the right headless flag
        try:
            result = subprocess.run(
                ["reg", "query",
                 r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon",
                 "/v", "version"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            ver_line = [l for l in result.stdout.splitlines() if "version" in l.lower()]
            major = int(ver_line[0].strip().split()[-1].split(".")[0]) if ver_line else 999
        except Exception:
            major = 999
        if major >= 112:
            options.add_argument("--headless=new")
        else:
            options.add_argument("--headless")
    # else: DEBUG_VISIBLE=True → no headless flag, Chrome opens visibly

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--window-position=-32000,-32000")  # off-screen fallback
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    # ── Anti-bot-detection ───────────────────────────────────────────────
    # Remove automation flags that Google detects
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # Spoof a real browser UA
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    try:
        driver_path = ChromeDriverManager().install()
    except Exception:
        import sys
        base = sys._MEIPASS if hasattr(sys, "_MEIPASS") else os.path.dirname(sys.executable)
        driver_path = os.path.join(base, "chromedriver.exe")

    # Hide both the chromedriver console window AND Chrome's brief startup flash.
    # CREATE_NO_WINDOW suppresses chromedriver; STARTUPINFO with SW_HIDE suppresses Chrome.
    service = Service(driver_path, log_path=os.devnull)
    try:
        import ctypes
        STARTUPINFO = subprocess.STARTUPINFO()
        STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        STARTUPINFO.wShowWindow = 0  # SW_HIDE
        service.creationflags = subprocess.CREATE_NO_WINDOW
        service._startupinfo = STARTUPINFO
    except Exception:
        try:
            service.creationflags = subprocess.CREATE_NO_WINDOW
        except AttributeError:
            pass

    driver = webdriver.Chrome(service=service, options=options)

    # Patch multiple fingerprint checks Google uses for bot detection
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        // 1. Remove navigator.webdriver flag
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

        // 2. Restore plugins array (headless Chrome has 0 plugins)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // 3. Restore languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // 4. Fix chrome object missing in headless
        window.chrome = { runtime: {} };

        // 5. Fix Notification.permission (headless returns 'denied')
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    """})

    return driver


def _is_email_field(inp, driver) -> bool:
    """Return True if this input is an email field (by type or by label text)."""
    try:
        if inp.get_attribute("type") == "email":
            return True
    except Exception:
        pass
    try:
        block = inp.find_element(By.XPATH, "./ancestor::div[@role='listitem']")
        labels = block.find_elements(By.CSS_SELECTOR, "span[dir='auto']")
        for lbl_el in labels:
            txt = lbl_el.text.lower()
            if any(kw in txt for kw in ("email", "e-mail", "بريد", "correo", "courriel")):
                return True
    except Exception:
        pass
    return False


def _get_question_label(el, driver) -> str:
    """Walk up to the listitem ancestor and grab the question title span."""
    try:
        block = el.find_element(By.XPATH, "./ancestor::div[@role='listitem']")
        spans = block.find_elements(By.CSS_SELECTOR, "span[dir='auto']")
        for s in spans:
            txt = s.text.strip()
            if txt:
                return txt
    except Exception:
        pass
    return "Question"


def _click_el(driver, el):
    """Scroll element into view then JS-click it."""
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.12)
    driver.execute_script("arguments[0].click();", el)
    time.sleep(0.18)


def fill_questions(driver, bias: float, use_email: bool, answer_tracker: dict, log_fn=None):
    """Fill every visible question on the current form page."""

    # ── 1. Text / Email / Textarea ────────────────────────────────────────
    # Google Forms renders "Other" radio text boxes as plain text inputs inside
    # the radio option container — we must skip those here and let the radio
    # handler deal with them after selecting the option.
    for inp in driver.find_elements(By.CSS_SELECTOR,
                                    "input[type='email'], input[type='text'], textarea"):
        try:
            if not inp.is_displayed():
                continue
            # Skip "Other" text boxes that belong to a radio/checkbox option —
            # they sit inside a div[data-value='__other_option__'] ancestor.
            try:
                inp.find_element(By.XPATH,
                    "./ancestor::div[@data-value='__other_option__']")
                continue  # will be handled by radio/checkbox block
            except Exception:
                pass
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            inp.clear()
            if _is_email_field(inp, driver):
                inp.send_keys(random_email() if use_email else random_name())
            else:
                inp.send_keys(random_name())
            time.sleep(0.15)
        except Exception:
            continue

    # ── 2. Date fields ────────────────────────────────────────────────────
    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='date']"):
        try:
            if not inp.is_displayed():
                continue
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            inp.send_keys(random_date())
            time.sleep(0.15)
        except Exception:
            continue

    # ── 3. Time fields ────────────────────────────────────────────────────
    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='time']"):
        try:
            if not inp.is_displayed():
                continue
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            inp.send_keys(random_time())
            time.sleep(0.15)
        except Exception:
            continue

    # ── 4. Radio buttons (multiple choice + linear scale) ─────────────────
    # Google Forms uses div[role='radiogroup'] containing div[role='radio'] items.
    # Each item may have a data-value='__other_option__' for the "Other" option.
    for group in driver.find_elements(By.CSS_SELECTOR, "div[role='radiogroup']"):
        try:
            options = group.find_elements(By.CSS_SELECTOR, "div[role='radio']")
            if not options:
                continue
            q_label = _get_question_label(group, driver)

            # Filter out the "__other_option__" from biased selection so we don't
            # accidentally pick Other when normal options exist.
            normal_opts = [o for o in options
                           if o.get_attribute("data-value") != "__other_option__"]
            other_opt   = next((o for o in options
                                if o.get_attribute("data-value") == "__other_option__"), None)

            pool   = normal_opts if normal_opts else options
            choice = biased_choice(pool, bias)

            label  = (choice.get_attribute("aria-label")
                      or choice.get_attribute("data-value")
                      or f"Option {pool.index(choice)+1}")

            if q_label not in answer_tracker:
                answer_tracker[q_label] = {}
            answer_tracker[q_label][label] = answer_tracker[q_label].get(label, 0) + 1

            _click_el(driver, choice)

            # If the chosen option IS "Other", fill its text box
            if choice is other_opt:
                try:
                    txt_box = choice.find_element(By.CSS_SELECTOR, "input[type='text']")
                    txt_box.clear()
                    txt_box.send_keys(random_name())
                    time.sleep(0.15)
                except Exception:
                    pass
        except Exception:
            continue

    # ── 5. Checkboxes ─────────────────────────────────────────────────────
    # Iterate only TOP-LEVEL listitems (not nested ones).
    # Google Forms renders each checkbox option as its own listitem INSIDE
    # the group listitem — we must only process the outer one, otherwise we
    # click each box twice (once in the group pass, once per-item) which
    # unticks them.
    all_listitems = driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")
    for item in all_listitems:
        try:
            # Skip if this listitem is itself nested inside another listitem
            # (i.e. it's an individual checkbox option row, not the question)
            parent_items = item.find_elements(
                By.XPATH, "./ancestor::div[@role='listitem']")
            if parent_items:
                continue  # it's a child — skip, handled by its parent

            # Skip if this question is a radio group — already handled above
            if item.find_elements(By.CSS_SELECTOR, "div[role='radio']"):
                continue

            # Find checkboxes inside this top-level item
            boxes = item.find_elements(By.CSS_SELECTOR, "div[role='checkbox']")
            if not boxes:
                continue

            q_label = _get_question_label(item, driver)
            if q_label not in answer_tracker:
                answer_tracker[q_label] = {}

            normal_boxes = [b for b in boxes
                            if b.get_attribute("data-value") != "__other_option__"]
            other_box    = next((b for b in boxes
                                 if b.get_attribute("data-value") == "__other_option__"), None)
            if not normal_boxes:
                normal_boxes = boxes

            # Single-option (e.g. "Yes I agree") → always tick; multi → pick 1–3
            chosen = normal_boxes if len(normal_boxes) == 1 else \
                     random.sample(normal_boxes, random.randint(1, min(3, len(normal_boxes))))

            for box in chosen:
                lbl = (box.get_attribute("aria-label")
                       or box.get_attribute("data-value")
                       or "Option")
                answer_tracker[q_label][lbl] = answer_tracker[q_label].get(lbl, 0) + 1
                _click_el(driver, box)
                if box is other_box:
                    try:
                        txt_box = box.find_element(By.CSS_SELECTOR, "input[type='text']")
                        txt_box.clear()
                        txt_box.send_keys(random_name())
                        time.sleep(0.15)
                    except Exception:
                        pass
        except Exception:
            continue

    # ── 6. Dropdowns ──────────────────────────────────────────────────────
    for dropdown in driver.find_elements(By.CSS_SELECTOR, "div[role='listbox']"):
        try:
            if not dropdown.is_displayed():
                continue
            q_label = _get_question_label(dropdown, driver)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dropdown)
            driver.execute_script("arguments[0].click();", dropdown)
            time.sleep(0.5)
            options = driver.find_elements(By.CSS_SELECTOR, "div[role='option']")
            valid = [o for o in options
                     if o.get_attribute("data-value") not in ("", None, "__other_option__")]
            if valid:
                choice = biased_choice(valid, bias)
                lbl = choice.get_attribute("data-value") or choice.text or "Option"
                if q_label not in answer_tracker:
                    answer_tracker[q_label] = {}
                answer_tracker[q_label][lbl] = answer_tracker[q_label].get(lbl, 0) + 1
                driver.execute_script("arguments[0].click();", choice)
                time.sleep(0.2)
        except Exception:
            continue


def handle_next_buttons(driver, wait, bias, use_email, answer_tracker, log_fn=None) -> bool:
    clicked = False
    while True:
        try:
            next_btn = None
            for btn in driver.find_elements(By.CSS_SELECTOR, "div[role='button']"):
                jsname = btn.get_attribute("jsname") or ""
                text = btn.text.strip().lower()
                if jsname == "OCpkoe" or "محو" in btn.text or "clear" in text:
                    continue
                if jsname == "sFsBmd" or "next" in text or "التالي" in text or "suivant" in text:
                    next_btn = btn
                    break
            if next_btn and next_btn.is_displayed():
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(1.5)
                clicked = True
                fill_questions(driver, bias, use_email, answer_tracker, log_fn=log_fn)
            else:
                break
        except Exception:
            break
    return clicked


def fill_and_submit(driver, form_url, bias, use_email, answer_tracker,
                    log_fn=None) -> bool:
    def _log(msg):
        if log_fn:
            log_fn(msg, "info")

    _log(f"  → Loading form page…")
    driver.get(form_url)
    wait = WebDriverWait(driver, 20)
    original_url = driver.current_url

    # Wait for form to fully render
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='listitem']")))
        # Also wait for at least one input to be present and interactable
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
            "input[type='text'], input[type='email'], textarea, div[role='radio'], div[role='checkbox']")))
    except Exception:
        _log("  ⚠ Timed out waiting for form questions to appear")
    time.sleep(2.0)  # extra settle — avoids race where inputs exist but aren't yet interactive

    q_count = len(driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']"))
    _log(f"  → Found {q_count} question block(s) on page")

    fill_questions(driver, bias, use_email, answer_tracker, log_fn=log_fn)
    _log("  → Questions filled")
    handle_next_buttons(driver, wait, bias, use_email, answer_tracker, log_fn=log_fn)
    _log("  → Multi-page navigation done")

    # Dismiss any open dialog
    try:
        for dialog in driver.find_elements(By.CSS_SELECTOR, "div[role='dialog']"):
            if dialog.is_displayed():
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.5)
                break
    except Exception:
        pass

    # Scroll to bottom so submit button is in viewport
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.8)

    submit_btn = None

    # 1st: exact jsname Google Forms uses for the Submit button
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, "div[role='button'][jsname='M2UYVd']")
        for b in btns:
            if b.is_displayed() and b.is_enabled():
                submit_btn = b
                break
    except Exception:
        pass

    # 2nd: button text contains a submit keyword (multi-language)
    if not submit_btn:
        submit_kw = ("submit", "إرسال", "envoyer", "enviar", "absenden",
                     "invia", "送信", "제출", "提交", "отправить", "gönder")
        try:
            for b in driver.find_elements(By.CSS_SELECTOR, "div[role='button']"):
                jsname = b.get_attribute("jsname") or ""
                if jsname == "OCpkoe":
                    continue
                txt = b.text.strip().lower()
                if any(kw in txt for kw in submit_kw) and b.is_displayed():
                    submit_btn = b
                    break
        except Exception:
            pass

    # 3rd: last visible, non-clear button on the page
    if not submit_btn:
        try:
            candidates = [
                b for b in driver.find_elements(By.CSS_SELECTOR, "div[role='button']")
                if b.is_displayed()
                and (b.get_attribute("jsname") or "") not in ("OCpkoe",)
                and "clear" not in b.text.lower()
                and "محو" not in b.text
            ]
            if candidates:
                submit_btn = candidates[-1]
        except Exception:
            pass

    submitted = False
    if submit_btn:
        _log(f"  → Submit button found (text: '{submit_btn.text.strip()[:30]}')")
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
            time.sleep(0.4)
            try:
                submit_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", submit_btn)
            submitted = True
            _log("  → Submit clicked")
        except Exception as e:
            _log(f"  ⚠ Submit click failed: {e}")
    else:
        _log("  ⚠ No submit button found — trying Enter key")

    if not submitted:
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.RETURN)
            submitted = True
            _log("  → Enter key sent as fallback")
        except Exception:
            pass

    # Give the page a moment to start transitioning before we poll
    time.sleep(1.5)

    # Confirm submission: look for confirmation elements OR URL change
    # We do NOT use "not find_elements(listitem)" alone — too fragile during page transition
    def _confirmed(d):
        if d.current_url != original_url:
            return True
        if d.find_elements(By.CSS_SELECTOR, "div[jsname='T4tBRd']"):
            return True
        if d.find_elements(By.CSS_SELECTOR, "div[jsname='dSBIn']"):
            return True
        if d.find_elements(By.CSS_SELECTOR,
                           "div.freebirdFormviewerViewResponseConfirmationMessage"):
            return True
        # Only use listitem absence as a signal if NO listitems AND no form inputs remain
        listitems = d.find_elements(By.CSS_SELECTOR, "div[role='listitem']")
        inputs = d.find_elements(By.CSS_SELECTOR, "input, textarea")
        if not listitems and not inputs:
            return True
        return False

    try:
        WebDriverWait(driver, 15).until(_confirmed)
        _log("  → Submission confirmed ✅")
        return True
    except Exception:
        # If still on form with a clear button visible → likely failed
        try:
            driver.find_element(By.CSS_SELECTOR, "div[role='button'][jsname='OCpkoe']")
            _log("  ⚠ Still on form — submission likely failed")
            return False
        except Exception:
            return submitted  # assume success if we did click something


def take_screenshot(driver, index: int) -> str:
    try:
        folder = os.path.join(os.path.expanduser("~"), "pgfb_screenshots")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"fail_{index}_{int(time.time())}.png")
        driver.save_screenshot(path)
        return path
    except Exception:
        return ""

# ─────────────────────────────────────────────
# ROUNDED WIDGET HELPERS
# ─────────────────────────────────────────────

def _rr(canvas, x1, y1, x2, y2, r, tags="rr", **kw):
    """Draw a smooth rounded rectangle on a Canvas."""
    canvas.create_arc(x1,       y1,       x1+2*r, y1+2*r, start=90,  extent=90, tags=tags, **kw)
    canvas.create_arc(x2-2*r,   y1,       x2,     y1+2*r, start=0,   extent=90, tags=tags, **kw)
    canvas.create_arc(x1,       y2-2*r,   x1+2*r, y2,     start=180, extent=90, tags=tags, **kw)
    canvas.create_arc(x2-2*r,   y2-2*r,   x2,     y2,     start=270, extent=90, tags=tags, **kw)
    canvas.create_rectangle(x1+r, y1,   x2-r, y2,   tags=tags, **kw)
    canvas.create_rectangle(x1,   y1+r, x2,   y2-r, tags=tags, **kw)


class RoundedCard(tk.Canvas):
    """A Card-like widget with rounded corners that hosts an inner tk.Frame."""

    def __init__(self, master, radius=12, fill="#2a2a3d", outer="#1e1e2e",
                 pad=14, **kw):
        kw.update(highlightthickness=0, bd=0, bg=outer)
        super().__init__(master, **kw)
        self._r     = radius
        self._fill  = fill
        self._outer = outer
        self._pad   = pad
        self._frame = tk.Frame(self, bg=fill)
        self._wid   = self.create_window(pad, pad, window=self._frame, anchor="nw")
        self.bind("<Configure>", self._redraw)

    def _redraw(self, e=None):
        self.delete("rr")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 6 or h < 6:
            return
        kw = dict(fill=self._fill, outline=self._fill)
        _rr(self, 0, 0, w, h, self._r, **kw)
        self.tag_lower("rr")
        p = self._pad
        self.itemconfig(self._wid, width=w - p*2, height=h - p*2)

    @property
    def inner(self):
        return self._frame

    def set_colors(self, fill, outer):
        self._fill  = fill
        self._outer = outer
        self._frame.configure(bg=fill)
        self.configure(bg=outer)
        self._redraw()


class RoundedBtn(tk.Canvas):
    """A Canvas-based button with rounded corners and hover effect."""

    def __init__(self, master, text="", radius=8, bg="#7c3aed", fg="white",
                 font=("Segoe UI", 10, "bold"), command=None,
                 padx=20, pady=9, outer_bg="#1e1e2e", **kw):
        import tkinter.font as tkfont
        kw.update(highlightthickness=0, bd=0, bg=outer_bg, cursor="hand2")
        super().__init__(master, **kw)
        self._text    = text
        self._r       = radius
        self._bg      = bg
        self._fg      = fg
        self._font    = font
        self._command = command
        self._state   = "normal"
        self._hover   = False

        f  = tkfont.Font(family=font[0], size=font[1],
                         weight=font[2] if len(font) > 2 else "normal")
        tw = f.measure(text)
        th = f.metrics("linespace")
        self.configure(width=tw + padx*2, height=th + pady*2)

        self.bind("<Configure>", self._draw)
        self.bind("<Enter>",     lambda e: self._set_hover(True))
        self.bind("<Leave>",     lambda e: self._set_hover(False))
        self.bind("<Button-1>",  self._click)

    def _dim(self, color, amt=25):
        try:
            r = max(0, int(color[1:3], 16) - amt)
            g = max(0, int(color[3:5], 16) - amt)
            b = max(0, int(color[5:7], 16) - amt)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return color

    def _draw(self, e=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        if self._state == "disabled":
            fill, fg = "#2d3748", "#4b5563"
        elif self._hover:
            fill, fg = self._dim(self._bg), self._fg
        else:
            fill, fg = self._bg, self._fg
        kw = dict(fill=fill, outline=fill)
        _rr(self, 0, 0, w, h, self._r, **kw)
        self.create_text(w//2, h//2, text=self._text, fill=fg,
                         font=self._font, anchor="center")

    def _set_hover(self, val):
        self._hover = val
        self._draw()

    def _click(self, e):
        if self._state == "normal" and self._command:
            self._command()

    def configure(self, **kw):
        redraw = False
        # outer_bg → canvas background (the area outside the rounded rect)
        if "outer_bg" in kw:
            super().configure(bg=kw.pop("outer_bg"))
        for key in ("state", "bg", "background", "fg", "foreground", "text", "command"):
            if key in kw:
                val = kw.pop(key)
                if key == "state":                self._state   = val; redraw = True
                elif key in ("bg", "background"): self._bg      = val; redraw = True
                elif key in ("fg", "foreground"): self._fg      = val; redraw = True
                elif key == "text":               self._text    = val; redraw = True
                elif key == "command":            self._command = val
        if kw:
            super().configure(**kw)
        if redraw:
            self._draw()

    def cget(self, key):
        if key == "text":  return self._text
        if key == "state": return self._state
        return super().cget(key)


# ─────────────────────────────────────────────
# PIE CHART CANVAS
# ─────────────────────────────────────────────

def draw_pie(canvas: tk.Canvas, data: dict, width: int, height: int, theme: dict):
    canvas.delete("all")
    canvas.configure(bg=theme["card"])

    if not data:
        canvas.create_text(width//2, height//2, text="No data yet",
                           fill=theme["subfg"], font=("Segoe UI", 11))
        return

    total = sum(data.values())
    if total == 0:
        return

    cx, cy, r = width // 2, height // 2 - 20, min(width, height) // 3
    start = 0.0

    items = list(data.items())
    for i, (label, count) in enumerate(items):
        extent = 360 * count / total
        color  = CHART_COLORS[i % len(CHART_COLORS)]
        canvas.create_arc(cx-r, cy-r, cx+r, cy+r,
                          start=start, extent=extent,
                          fill=color, outline=theme["card"], width=2)
        # Label on slice
        mid_angle = math.radians(start + extent / 2)
        lx = cx + (r * 0.65) * math.cos(mid_angle)
        ly = cy - (r * 0.65) * math.sin(mid_angle)
        pct = f"{100*count/total:.0f}%"
        canvas.create_text(lx, ly, text=pct, fill="white",
                           font=("Segoe UI", 8, "bold"))
        start += extent

    # Legend
    lx, ly = 10, height - (len(items) * 18) - 10
    for i, (label, count) in enumerate(items):
        color = CHART_COLORS[i % len(CHART_COLORS)]
        canvas.create_rectangle(lx, ly, lx+12, ly+12, fill=color, outline="")
        canvas.create_text(lx+18, ly+6, text=f"{label} ({count})",
                           anchor="w", fill=theme["fg"], font=("Segoe UI", 8))
        ly += 18


class ChartWindow:
    def __init__(self, parent, theme: dict):
        self.win = tk.Toplevel(parent)
        self.win.title("Live Answer Distribution")
        self.win.configure(bg=theme["bg"])
        self.win.resizable(True, True)
        self.theme    = theme
        self.data     = {}       # {question: {option: count}}
        self.page     = 0
        self.canvases = {}
        self._lock    = threading.Lock()

        self.win.geometry("520x440")

        # Header
        self.title_var = tk.StringVar(value="No data yet")
        tk.Label(self.win, textvariable=self.title_var,
                 font=("Segoe UI", 11, "bold"),
                 bg=theme["bg"], fg=theme["fg"]).pack(pady=(12, 4))

        # Canvas
        self.canvas = tk.Canvas(self.win, bg=theme["card"],
                                highlightthickness=0, width=500, height=320)
        self.canvas.pack(padx=12, pady=4, fill="both", expand=True)

        # Nav row
        nav = tk.Frame(self.win, bg=theme["bg"])
        nav.pack(pady=8)
        self.prev_btn = tk.Button(nav, text="◀ Prev", font=("Segoe UI", 9),
                                  bg=theme["card"], fg=theme["fg"], relief="flat",
                                  padx=12, pady=4, command=self.prev_page)
        self.prev_btn.pack(side="left", padx=6)
        self.page_var = tk.StringVar(value="")
        tk.Label(nav, textvariable=self.page_var,
                 font=("Segoe UI", 9), bg=theme["bg"], fg=theme["subfg"]).pack(side="left", padx=6)
        self.next_btn = tk.Button(nav, text="Next ▶", font=("Segoe UI", 9),
                                  bg=theme["card"], fg=theme["fg"], relief="flat",
                                  padx=12, pady=4, command=self.next_page)
        self.next_btn.pack(side="left", padx=6)

        self._refresh()

    def update_data(self, new_data: dict):
        with self._lock:
            self.data = {k: dict(v) for k, v in new_data.items()}
        self.win.after(0, self._refresh)

    def _refresh(self):
        questions = list(self.data.keys())
        if not questions:
            self.title_var.set("Waiting for first submission…")
            self.page_var.set("")
            draw_pie(self.canvas, {}, 500, 320, self.theme)
            return
        self.page = max(0, min(self.page, len(questions) - 1))
        q = questions[self.page]
        self.title_var.set(q)
        self.page_var.set(f"Question {self.page+1} of {len(questions)}")
        w = self.canvas.winfo_width()  or 500
        h = self.canvas.winfo_height() or 320
        draw_pie(self.canvas, self.data.get(q, {}), w, h, self.theme)
        self.prev_btn.configure(state="normal" if self.page > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.page < len(questions)-1 else "disabled")

    def prev_page(self):
        self.page = max(0, self.page - 1)
        self._refresh()

    def next_page(self):
        self.page = min(len(self.data) - 1, self.page + 1)
        self._refresh()

# ─────────────────────────────────────────────
# SYSTEM TRAY
# ─────────────────────────────────────────────

def make_tray_icon(root: tk.Tk):
    if not TRAY_AVAILABLE:
        return None
    try:
        img = Image.new("RGB", (64, 64), color="#7c3aed")
        d   = ImageDraw.Draw(img)
        d.ellipse([8, 8, 56, 56], fill="#e2e8f0")
        d.text((20, 18), "🤖", fill="#7c3aed")

        def on_show(icon, item):
            icon.stop()
            root.after(0, root.deiconify)

        menu  = pystray.Menu(pystray.MenuItem("Show", on_show, default=True))
        icon  = pystray.Icon("pgfb", img, "Pigeons Funny Google Forum Bot", menu)
        return icon
    except Exception:
        return None

# ─────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────

class BotGUI:
    def __init__(self, root: tk.Tk):
        self.root         = root
        self.root.title("Pigeons Funny Google Forum Bot")
        self.root.resizable(False, False)
        self.root.geometry("780x900")
        self._theme_name  = "Dark"
        self._t           = THEMES["Dark"]
        self._chart_win   = None
        self._answer_data = {}
        self._tray_icon   = None
        self._running     = False
        self._driver      = None   # kept here so _on_close can quit it
        self._successes   = 0
        self._failures    = 0
        self._total       = 0

        # References to themed widgets (filled in _build_ui)
        self._cards:  list = []   # RoundedCard instances
        self._labels: list = []   # (Label, role) where role ∈ "title","sub","card","subfg"
        self._inputs: list = []   # Entry / Text / Spinbox
        self._scales: list = []   # Scale
        self._checks: list = []   # Checkbutton
        self._rbtns:  list = []   # (RoundedBtn, role-str)

        cfg = load_config()
        self._build_ui(cfg)
        self._apply_theme()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── build ──────────────────────────────────────────────────────────────
    def _build_ui(self, cfg: dict):
        root  = self.root
        t     = self._t
        PAD   = 14
        FONT  = ("Segoe UI", 10)
        FONTB = ("Segoe UI", 10, "bold")

        def card(parent, **kw):
            c = RoundedCard(parent, radius=14, fill=t["card"], outer=t["bg"],
                            pad=14, **kw)
            self._cards.append(c)
            return c

        def lbl(parent, text, role="card", **kw):
            w = tk.Label(parent, text=text, **kw)
            self._labels.append((w, role))
            return w

        def entry(parent, **kw):
            w = tk.Entry(parent, relief="flat", bd=4, **kw)
            self._inputs.append(w)
            return w

        def spinbox(parent, **kw):
            w = tk.Spinbox(parent, relief="flat", bd=4, **kw)
            self._inputs.append(w)
            return w

        def rbtn(parent, text, bg, command, role="", padx=22):
            b = RoundedBtn(parent, text=text, radius=10, bg=bg, fg="white",
                           font=FONTB, command=command, padx=padx, pady=9,
                           outer_bg=t["bg"])
            self._rbtns.append((b, role))
            return b

        # ── Header (title centred; theme toggle pinned top-right) ─────────
        hdr = tk.Frame(root, bg=t["bg"])
        hdr.pack(fill="x", pady=(12, 4))
        hdr.columnconfigure(0, weight=1)   # left spacer
        hdr.columnconfigure(1, weight=0)   # centre column
        hdr.columnconfigure(2, weight=1)   # right column (theme btn)

        centre = tk.Frame(hdr, bg=t["bg"])
        centre.grid(row=0, column=1)
        self.title_lbl = lbl(centre, "🤖  Pigeons Funny Google Forum Bot",
                             role="title",
                             font=("Segoe UI", 14, "bold"), bg=t["bg"], fg=t["fg"])
        self.title_lbl.pack()
        self.sub_lbl = lbl(centre, "Automates form submissions with randomized answers",
                           role="sub",
                           font=("Segoe UI", 9), bg=t["bg"], fg=t["subfg"])
        self.sub_lbl.pack(pady=(2, 0))

        # Theme button lives in the top-right corner of the header
        right = tk.Frame(hdr, bg=t["bg"])
        right.grid(row=0, column=2, sticky="ne", padx=(0, PAD), pady=4)
        self._labels.append((right, "title"))  # keep bg in sync
        self.theme_btn = rbtn(right, "☀  Light", "#334155", self.toggle_theme, "theme", padx=14)
        self.theme_btn.pack(anchor="ne")

        # ── URL card ──────────────────────────────────────────────────────
        url_c = card(root, height=110)
        url_c.pack(fill="x", padx=PAD, pady=(10, 6))
        fi = url_c.inner
        lbl(fi, "Form URL", role="card_bold",
            font=FONTB, bg=t["card"], fg=t["fg"]).pack(anchor="w")
        lbl(fi, "Paste your Google Form link (full or shortened forms.gle)",
            role="card_sub",
            font=("Segoe UI", 8), bg=t["card"], fg=t["subfg"]).pack(anchor="w", pady=(1, 6))
        self.url_var = tk.StringVar(value="")
        self.url_entry = entry(fi, textvariable=self.url_var,
                               font=FONT, width=60)
        self.url_entry.pack(fill="x", ipady=5)

        # ── Settings row (3 cards) ────────────────────────────────────────
        srow = tk.Frame(root, bg=t["bg"])
        srow.pack(fill="x", padx=PAD, pady=(0, 6))
        srow.columnconfigure(0, weight=1)
        srow.columnconfigure(1, weight=1)
        srow.columnconfigure(2, weight=1)

        # Submissions
        cnt_c = card(srow, height=80)
        cnt_c.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        fi = cnt_c.inner
        lbl(fi, "Submissions", role="card_bold",
            font=FONTB, bg=t["card"], fg=t["fg"]).pack(anchor="w")
        self.count_var = tk.IntVar(value=SUBMIT_COUNT)
        self.count_spin = spinbox(fi, from_=1, to=500, textvariable=self.count_var,
                                  font=FONT, width=8)
        self.count_spin.pack(anchor="w", pady=(6, 0))

        # Max Retries
        ret_c = card(srow, height=80)
        ret_c.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
        fi = ret_c.inner
        lbl(fi, "Max Retries", role="card_bold",
            font=FONTB, bg=t["card"], fg=t["fg"]).pack(anchor="w")
        self.retry_var = tk.IntVar(value=cfg.get("max_retries", MAX_RETRIES))
        self.retry_spin = spinbox(fi, from_=0, to=5, textvariable=self.retry_var,
                                  font=FONT, width=8)
        self.retry_spin.pack(anchor="w", pady=(6, 0))

        # Speed
        spd_c = card(srow, height=80)
        spd_c.grid(row=0, column=2, sticky="nsew")
        fi = spd_c.inner
        lbl(fi, "Speed", role="card_bold",
            font=FONTB, bg=t["card"], fg=t["fg"]).pack(anchor="w")
        self.speed_var = tk.StringVar(value=cfg.get("speed", "Normal"))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
                        fieldbackground=t["input"], background=t["card"],
                        foreground=t["fg"], selectforeground=t["fg"],
                        selectbackground=t["input"],
                        bordercolor=t["card"], arrowcolor=t["fg"])
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", t["input"])],
                  foreground=[("readonly", t["fg"])],
                  selectforeground=[("readonly", t["fg"])],
                  selectbackground=[("readonly", t["input"])],
                  background=[("readonly", t["card"])])
        self.speed_menu = ttk.Combobox(fi, textvariable=self.speed_var,
                                       values=list(SPEED_PRESETS.keys()),
                                       state="readonly", width=11, font=FONT,
                                       style="Dark.TCombobox")
        self.speed_menu.pack(anchor="w", pady=(6, 0))

        # ── Answer Bias card ──────────────────────────────────────────────
        bias_c = card(root, height=110)
        bias_c.pack(fill="x", padx=PAD, pady=(0, 6))
        fi = bias_c.inner
        lbl(fi, "Answer Bias", role="card_bold",
            font=FONTB, bg=t["card"], fg=t["fg"]).pack(anchor="w")
        lbl(fi, "Lean toward first options  —  Random  —  Lean toward last options",
            role="card_sub",
            font=("Segoe UI", 8), bg=t["card"], fg=t["subfg"]).pack(anchor="w", pady=(1, 5))
        slider_row = tk.Frame(fi, bg=t["card"])
        slider_row.pack(fill="x")
        self._labels.append((slider_row, "card_frame"))
        lbl(slider_row, "First", role="card_sub",
            font=("Segoe UI", 8), bg=t["card"], fg=t["subfg"]).pack(side="left")
        self.bias_var = tk.DoubleVar(value=0.0)
        self.bias_slider = tk.Scale(
            slider_row, from_=-1.0, to=1.0, resolution=0.01,
            orient="horizontal", variable=self.bias_var,
            highlightthickness=0, showvalue=False,
            command=self._update_bias_label,
            troughcolor=t["input"], bg=t["card"], fg=t["fg"],
            activebackground=t["accent"], sliderlength=18,
        )
        self._scales.append(self.bias_slider)
        self.bias_slider.pack(side="left", padx=8, fill="x", expand=True)
        lbl(slider_row, "Last", role="card_sub",
            font=("Segoe UI", 8), bg=t["card"], fg=t["subfg"]).pack(side="left")
        self.bias_label_var = tk.StringVar(value="Random (neutral)")
        self.bias_val_lbl = tk.Label(fi, textvariable=self.bias_label_var,
                                     font=("Segoe UI", 9, "bold"),
                                     bg=t["card"], fg=t["accent"])
        self.bias_val_lbl.pack(anchor="w", pady=(5, 0))

        # Email toggle (inside a small pill-style frame below bias card)
        tog_frame = tk.Frame(root, bg=t["bg"])
        tog_frame.pack(fill="x", padx=PAD, pady=(0, 6))
        self.email_var = tk.BooleanVar(value=cfg.get("use_email", True))
        self.email_toggle = tk.Checkbutton(
            tog_frame, text="  Generate fake emails for email fields",
            variable=self.email_var, font=("Segoe UI", 9),
            bg=t["bg"], fg=t["subfg"], activebackground=t["bg"],
            activeforeground=t["fg"], selectcolor=t["card"],
            relief="flat", cursor="hand2",
        )
        self._checks.append(self.email_toggle)
        self.email_toggle.pack(side="left")

        # ── Progress card ─────────────────────────────────────────────────
        prog_c = card(root, height=140)
        prog_c.pack(fill="x", padx=PAD, pady=(0, 6))
        fi = prog_c.inner

        stats_row = tk.Frame(fi, bg=t["card"])
        self._labels.append((stats_row, "card_frame"))
        stats_row.pack(fill="x", pady=(0, 12))
        self._stat(stats_row, "Submitted", "0",        0)
        self._stat(stats_row, "Failed",    "0",        1)
        self._stat(stats_row, "Remaining", str(SUBMIT_COUNT), 2)
        self._stat(stats_row, "Progress",  "0%",       3)

        style.configure("Bot.Horizontal.TProgressbar",
                        troughcolor=t["input"], background=t["accent"],
                        bordercolor=t["card"], lightcolor=t["accent"],
                        darkcolor=t["accent"], thickness=10)
        self.progress_var = tk.DoubleVar(value=0)
        self.prog_bar = ttk.Progressbar(fi, variable=self.progress_var,
                                        maximum=100,
                                        style="Bot.Horizontal.TProgressbar")
        self.prog_bar.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready — paste a URL and click Start")
        self.status_lbl = lbl(fi, "", role="card_sub",
                              font=("Segoe UI", 9), bg=t["card"], fg=t["subfg"])
        self.status_lbl.configure(textvariable=self.status_var)
        self.status_lbl.pack(anchor="w", pady=(6, 0))

        # ── Log card (expands to fill space) ─────────────────────────────
        log_c = card(root)
        log_c.pack(fill="both", expand=True, padx=PAD, pady=(0, 6))
        fi = log_c.inner
        lbl(fi, "Log", role="card_bold",
            font=FONTB, bg=t["card"], fg=t["fg"]).pack(anchor="w", pady=(0, 6))
        log_frame = tk.Frame(fi, bg=t["card"])
        self._labels.append((log_frame, "card_frame"))
        log_frame.pack(fill="both", expand=True)
        self.log_box = tk.Text(log_frame, height=7, font=("Consolas", 9),
                               relief="flat", state="disabled", wrap="word",
                               bg=t["input"], fg=t["fg"],
                               insertbackground=t["fg"], padx=6, pady=6)
        self._inputs.append(self.log_box)
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview,
                                 bg=t["card"], troughcolor=t["input"])
        self.log_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)

        # ── Single button row, BELOW log – fills full width equally ──────
        btn_row = tk.Frame(root, bg=t["bg"])
        btn_row.pack(fill="x", padx=PAD, pady=(6, PAD))
        for col in range(6):
            btn_row.columnconfigure(col, weight=1, uniform="btn")

        self.start_btn   = rbtn(btn_row, "▶  Start",    t["accent"], self.start,            "start", padx=4)
        self.test_btn    = rbtn(btn_row, "✓  Test Run", "#0f766e",   self.test_run,          "test",  padx=4)
        self.history_btn = rbtn(btn_row, "☰  History",  "#334155",   self.show_history,      "hist",  padx=4)
        self.chart_btn   = rbtn(btn_row, "◉  Charts",   "#1d4ed8",   self.toggle_chart,      "chart", padx=4)
        self.tray_btn    = rbtn(btn_row, "⬇  Tray",     "#334155",   self.minimize_to_tray,  "tray",  padx=4)
        self.stop_btn    = rbtn(btn_row, "■  Stop",     "#374151",   self.stop,              "stop",  padx=4)
        self.stop_btn.configure(state="disabled")

        for col, b in enumerate((self.start_btn, self.test_btn, self.history_btn,
                                  self.chart_btn, self.tray_btn, self.stop_btn)):
            b.grid(row=0, column=col, sticky="ew",
                   padx=(0, 6) if col < 5 else (0, 0))

        if not TRAY_AVAILABLE:
            self.tray_btn.configure(state="disabled")

        # ── Sync Remaining stat with Submissions spinbox ──────────────────
        def _sync_remaining(*_):
            if not self._running:
                try:
                    self._remaining_var.set(str(self.count_var.get()))
                except Exception:
                    pass
        self.count_var.trace_add("write", _sync_remaining)

    # ── stat boxes ─────────────────────────────────────────────────────────
    def _stat(self, parent, label, value, col):
        t = self._t
        frame = tk.Frame(parent, bg=t["card"])
        frame.grid(row=0, column=col, sticky="w", padx=(0, 24))
        self._labels.append((frame, "card_frame"))
        color_map = {"Submitted": t["green"], "Failed": t["red"],
                     "Remaining": t["fg"],    "Progress": t["accent"]}
        color = color_map.get(label, t["fg"])
        var = tk.StringVar(value=value)
        num_lbl = tk.Label(frame, textvariable=var,
                           font=("Segoe UI", 22, "bold"), fg=color, bg=t["card"])
        num_lbl.pack(anchor="w")
        sub_lbl = tk.Label(frame, text=label,
                           font=("Segoe UI", 8), fg=t["subfg"], bg=t["card"])
        sub_lbl.pack(anchor="w")
        self._labels.append((num_lbl, "stat_val_" + label.lower()))
        self._labels.append((sub_lbl, "card_sub"))
        setattr(self, f"_{label.lower()}_var", var)
        setattr(self, f"_{label.lower()}_num_lbl", num_lbl)

    # ── theme ──────────────────────────────────────────────────────────────
    def _apply_theme(self):
        t = self._t
        self.root.configure(bg=t["bg"])

        # Root-level frames
        for w in self.root.winfo_children():
            if isinstance(w, tk.Frame):
                w.configure(bg=t["bg"])

        # Cards
        for c in self._cards:
            c.set_colors(t["card"], t["bg"])

        # Labels
        for w, role in self._labels:
            try:
                if role == "title":
                    w.configure(bg=t["bg"], fg=t["fg"])
                elif role == "sub":
                    w.configure(bg=t["bg"], fg=t["subfg"])
                elif role == "card_bold":
                    w.configure(bg=t["card"], fg=t["fg"])
                elif role == "card_sub":
                    w.configure(bg=t["card"], fg=t["subfg"])
                elif role == "card_frame":
                    w.configure(bg=t["card"])
                elif role.startswith("stat_val_"):
                    key = role[len("stat_val_"):]
                    color_map = {"submitted": t["green"], "failed": t["red"],
                                 "remaining": t["fg"],    "progress": t["accent"]}
                    w.configure(bg=t["card"], fg=color_map.get(key, t["fg"]))
            except Exception:
                pass

        # Inputs
        for w in self._inputs:
            cls = w.__class__.__name__
            try:
                if cls == "Text":
                    w.configure(bg=t["input"], fg=t["fg"])
                elif cls == "Spinbox":
                    w.configure(bg=t["input"], fg=t["fg"],
                                insertbackground=t["fg"],
                                buttonbackground=t["card"])
                else:
                    w.configure(bg=t["input"], fg=t["fg"],
                                insertbackground=t["fg"])
            except Exception:
                pass

        # Scales
        for w in self._scales:
            try:
                w.configure(bg=t["card"], fg=t["fg"], troughcolor=t["input"],
                            activebackground=t["accent"])
            except Exception:
                pass

        # Checkbuttons
        for w in self._checks:
            try:
                w.configure(bg=t["bg"], fg=t["subfg"],
                            activebackground=t["bg"], activeforeground=t["fg"],
                            selectcolor=t["card"])
            except Exception:
                pass

        # Rounded buttons — update canvas outer background; keep each btn's own color
        for btn, role in self._rbtns:
            try:
                btn.configure(outer_bg=t["bg"])
            except Exception:
                pass

        # Bias label accent
        self.bias_val_lbl.configure(bg=t["card"], fg=t["accent"])

        # Log tags
        self.log_box.tag_config("ok",   foreground=t["green"])
        self.log_box.tag_config("fail", foreground=t["red"])
        self.log_box.tag_config("warn", foreground=t["yellow"])
        self.log_box.tag_config("info", foreground=t["subfg"])
        self.log_box.tag_config("head", foreground=t["accent"])

        # Progress bar
        style = ttk.Style()
        style.configure("Bot.Horizontal.TProgressbar",
                        troughcolor=t["input"], background=t["accent"],
                        bordercolor=t["card"], lightcolor=t["accent"],
                        darkcolor=t["accent"])
        # Combobox
        style.configure("Dark.TCombobox",
                        fieldbackground=t["input"], background=t["card"],
                        foreground=t["fg"], selectforeground=t["fg"],
                        selectbackground=t["input"],
                        bordercolor=t["card"], arrowcolor=t["fg"])
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", t["input"])],
                  foreground=[("readonly", t["fg"])],
                  selectforeground=[("readonly", t["fg"])],
                  selectbackground=[("readonly", t["input"])],
                  background=[("readonly", t["card"])])

    def toggle_theme(self):
        self._theme_name = "Light" if self._theme_name == "Dark" else "Dark"
        self._t = THEMES[self._theme_name]
        self.theme_btn.configure(
            text="🌙  Dark" if self._theme_name == "Light" else "☀  Light")
        self._apply_theme()
        if self._chart_win and self._chart_win.win.winfo_exists():
            self._chart_win.theme = self._t
            self._chart_win._refresh()

    # ── bias label ─────────────────────────────────────────────────────────
    def _update_bias_label(self, val=None):
        v = self.bias_var.get()
        if abs(v) < 0.05:
            label = "Random (neutral)"
        elif v < -0.66:
            label = f"Strongly toward first ({v:.2f})"
        elif v < 0:
            label = f"Slightly toward first ({v:.2f})"
        elif v > 0.66:
            label = f"Strongly toward last ({v:.2f})"
        else:
            label = f"Slightly toward last ({v:.2f})"
        self.bias_label_var.set(label)

    # ── log ────────────────────────────────────────────────────────────────
    def log(self, msg, tag="info"):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n", tag)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _do)

    # ── stats ──────────────────────────────────────────────────────────────
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

    def _save_settings(self):
        save_config({
            "max_retries": self.retry_var.get(),
            "speed":       self.speed_var.get(),
            "use_email":   self.email_var.get(),
        })

    def _set_running(self, running: bool):
        self._running = running
        state = "disabled" if running else "normal"
        def _update():
            self.start_btn.configure(
                state=state,
                bg="#4b2e9e" if running else self._t["accent"])
            self.test_btn.configure(state=state)
            self.history_btn.configure(state=state)
            self.stop_btn.configure(
                state="normal" if running else "disabled",
                bg=self._t["red"] if running else "#374151")
        self.root.after(0, _update)

    # ── chart ──────────────────────────────────────────────────────────────
    def toggle_chart(self):
        if self._chart_win and self._chart_win.win.winfo_exists():
            self._chart_win.win.destroy()
            self._chart_win = None
        else:
            self._chart_win = ChartWindow(self.root, self._t)
            if self._answer_data:
                self._chart_win.update_data(self._answer_data)

    def _push_chart(self):
        if self._chart_win and self._chart_win.win.winfo_exists():
            self._chart_win.update_data(self._answer_data)

    # ── tray ───────────────────────────────────────────────────────────────
    def minimize_to_tray(self):
        if not TRAY_AVAILABLE:
            messagebox.showinfo("Tray", "Install pystray and Pillow to use this feature:\npip install pystray Pillow")
            return
        self.root.withdraw()
        icon = make_tray_icon(self.root)
        if icon:
            self._tray_icon = icon
            threading.Thread(target=icon.run, daemon=True).start()

    # ── validate url ───────────────────────────────────────────────────────
    def _validate_url(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Please paste a Google Form URL first.")
            return None
        if "docs.google.com/forms" not in url and "forms.gle" not in url and "goo.gl" not in url:
            messagebox.showerror("Invalid URL", "That doesn't look like a Google Forms link.")
            return None
        return url

    # ── start / test ───────────────────────────────────────────────────────
    def test_run(self):
        url = self._validate_url()
        if not url:
            return
        self._answer_data = {}
        self._total = 1
        self._successes = 0
        self._failures  = 0
        _refill_name_queue()
        self._submitted_var.set("0")
        self._failed_var.set("0")
        self._remaining_var.set("1")
        self._progress_var.set("0%")
        self.progress_var.set(0)
        self._set_running(True)
        self.status_var.set("Test run — 1 submission…")
        self.log("━━ TEST RUN (1 submission) ━━", "head")
        threading.Thread(target=self._run, args=(url, 1), daemon=True).start()

    def start(self):
        url = self._validate_url()
        if not url:
            return
        self._answer_data = {}
        self._total = self.count_var.get()
        self._successes = 0
        self._failures  = 0
        _refill_name_queue()
        self._submitted_var.set("0")
        self._failed_var.set("0")
        self._remaining_var.set(str(self._total))
        self._progress_var.set("0%")
        self.progress_var.set(0)
        self._set_running(True)
        self.status_var.set("Starting bot…")
        self._save_settings()
        self.log(f"━━ Starting {self._total} submissions ━━", "head")
        self.log(f"URL: {url}", "info")
        threading.Thread(target=self._run, args=(url, self._total), daemon=True).start()

    def stop(self):
        self._running = False
        self.status_var.set("Stopping after current submission…")
        self.log("⚠ Stop requested by user", "warn")

    def _on_close(self):
        """X button / Alt-F4 — kill Chrome immediately then destroy the window."""
        self._running = False          # signal the bot loop to exit
        try:
            if self._driver:
                self._driver.quit()    # closes all Chrome tabs/processes
                self._driver = None
        except Exception:
            pass
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception:
            pass
        self.root.destroy()

    # ── bot thread ─────────────────────────────────────────────────────────
    def _run(self, raw_url: str, count: int):
        driver = None
        try:
            self.root.after(0, lambda: self.status_var.set("Resolving URL…"))
            self.log("Resolving URL…", "info")
            form_url = resolve_url(raw_url)
            if form_url != raw_url:
                self.log(f"Expanded to: {form_url}", "info")

            self.root.after(0, lambda: self.status_var.set("Launching Chrome…"))
            self.log("Launching Chrome…", "info")
            try:
                driver = make_driver()
                self._driver = driver
                self.log("✅ Chrome launched successfully", "ok")
            except Exception as e:
                self.log(f"❌ Chrome failed to launch: {e}", "fail")
                self._set_running(False)
                self.root.after(0, lambda: self.status_var.set("Failed — Chrome could not launch"))
                return

            speed      = SPEED_PRESETS.get(self.speed_var.get(), SPEED_PRESETS["Normal"])
            bias       = self.bias_var.get()
            use_email  = self.email_var.get()
            max_retries = self.retry_var.get()

            for i in range(1, count + 1):
                if not self._running:
                    break

                self.root.after(0, lambda i=i: self.status_var.set(
                    f"Submitting {i} of {count}…"))
                self.log(f"[{i}/{count}] Submitting…", "info")

                success = False
                for attempt in range(max_retries + 1):
                    try:
                        ok = fill_and_submit(driver, form_url, bias,
                                             use_email, self._answer_data,
                                             log_fn=self.log)
                        if ok:
                            success = True
                            self._push_chart()
                            break
                        else:
                            if attempt < max_retries:
                                self.log(f"[{i}/{count}] ⚠ Not confirmed, retrying ({attempt+1}/{max_retries})…", "warn")
                            else:
                                screenshot = take_screenshot(driver, i)
                                self.log(f"[{i}/{count}] ❌ Failed after {max_retries} retries", "fail")
                                if screenshot:
                                    self.log(f"   📸 {screenshot}", "warn")
                    except Exception as e:
                        if attempt < max_retries:
                            self.log(f"[{i}/{count}] ⚠ Error retrying: {e}", "warn")
                        else:
                            screenshot = take_screenshot(driver, i)
                            self.log(f"[{i}/{count}] ❌ Error: {e}", "fail")
                            if screenshot:
                                self.log(f"   📸 {screenshot}", "warn")

                if success:
                    self._successes += 1
                    self.log(f"[{i}/{count}] ✅ Success", "ok")
                else:
                    self._failures += 1

                self._update_stats()

                if i < count and self._running:
                    delay = random.uniform(*speed)
                    self.root.after(0, lambda d=delay: self.status_var.set(
                        f"Waiting {d:.1f}s…"))
                    time.sleep(delay)

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            self._driver = None
            total_done = self._successes + self._failures
            append_history(raw_url, total_done, self._successes, self._failures)
            self.log(
                f"━━ Done: {self._successes} succeeded, "
                f"{self._failures} failed out of {total_done} attempts ━━", "head")
            self._set_running(False)
            self.root.after(0, lambda: self.status_var.set(
                f"Finished — {self._successes}/{total_done} confirmed"))

    # ── history ────────────────────────────────────────────────────────────
    def show_history(self):
        t = self._t
        try:
            if not os.path.exists(LOG_FILE):
                messagebox.showinfo("History", "No submission history yet.")
                return
            with open(LOG_FILE) as f:
                history = json.load(f)
        except Exception:
            messagebox.showerror("History", "Could not load history file.")
            return

        win = tk.Toplevel(self.root)
        win.title("Submission History")
        win.configure(bg=t["bg"])
        win.resizable(True, True)

        tk.Label(win, text="Submission History", font=("Segoe UI", 13, "bold"),
                 bg=t["bg"], fg=t["fg"]).pack(pady=(16, 4))

        frame = tk.Frame(win, bg=t["card"], padx=16, pady=10)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        box = tk.Text(frame, font=("Consolas", 9), bg=t["input"], fg=t["fg"],
                      relief="flat", wrap="none", width=72, height=20)
        sb  = tk.Scrollbar(frame, command=box.yview, bg=t["card"])
        box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)

        box.tag_config("ok",   foreground=t["green"])
        box.tag_config("fail", foreground=t["red"])
        box.tag_config("head", foreground=t["accent"])

        total_runs   = len(history)
        total_ok     = sum(e["succeeded"] for e in history)
        total_failed = sum(e["failed"] for e in history)
        rate         = f"{100*total_ok//(total_ok+total_failed)}%" if (total_ok+total_failed) > 0 else "N/A"

        box.insert("end", f"  Runs: {total_runs}   Total submitted: {total_ok+total_failed}   "
                           f"Success rate: {rate}\n\n", "head")
        box.insert("end", f"{'Date':<18} {'OK':<8} {'Fail':<8} {'Rate':<8} URL\n", "head")
        box.insert("end", "─" * 80 + "\n", "head")

        for entry in reversed(history):
            total = entry["succeeded"] + entry["failed"]
            r     = f"{100*entry['succeeded']//total}%" if total > 0 else "N/A"
            tag   = "ok" if entry["failed"] == 0 else "fail"
            line  = (f"{entry['date']:<18} "
                     f"{entry['succeeded']:<8} "
                     f"{entry['failed']:<8} "
                     f"{r:<8} "
                     f"{entry['url'][:35]}\n")
            box.insert("end", line, tag)

        box.configure(state="disabled")

        tk.Button(win, text="Clear History", font=("Segoe UI", 9),
                  bg=t["red"], fg="white", relief="flat", padx=12, pady=6,
                  command=lambda: self._clear_history(win)).pack(pady=8)

    def _clear_history(self, win):
        if messagebox.askyesno("Clear History", "Delete all submission history?"):
            try:
                os.remove(LOG_FILE)
            except Exception:
                pass
            win.destroy()
            messagebox.showinfo("History", "History cleared.")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app  = BotGUI(root)
    root.mainloop()
