import os
import re
import sys
import yaml
from typing import List
from database import init_db, set_settings, get_setting
from src.database import save_user_profile_to_user_db, get_user_db_path
from src.main import (
    CONFIG_PATH,
    load_preferences_config,
    update_preferences_config,
    run_job_search_pipeline,
)
from src.email_notifier import format_plain_text_digest
from install_12pm_autostart import setup_windows_startup_and_tasks

OPENCLAW_PROFILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "openclaw_agent",
    "job_profile.md",
)


def write_openclaw_profile_md(
    name: str,
    email: str,
    app_password: str,
    role: str,
    locations: List[str],
    sites: List[str],
) -> None:
    """
    Writes the user's Name, Gmail ID, App Password, Target Job Role, Locations,
    and Selected Sites into openclaw_agent/job_profile.md from the terminal setup.
    """
    os.makedirs(os.path.dirname(OPENCLAW_PROFILE_PATH), exist_ok=True)
    locs_bullets = "\n".join([f"- {loc}" for loc in locations]) if locations else "- Remote\n- Bengaluru"
    sites_bullets = "\n".join([f"- {s.title()}" for s in sites]) if sites else "- Greenhouse\n- Workday\n- Lever"

    content = f"""# Candidate Job Search & Gmail Profile

## 1. Gmail & Sign-In Credentials
- **Name**: {name}
- **Gmail Address**: {email}
- **Gmail 16-Char App Password**: {app_password or "NOT_SET"}
- **Portal Sign-In Email (for Workday/Lever/Greenhouse if prompted)**: {email}
- **Dedicated User DB**: `{get_user_db_path(email)}`

## 2. Target Job Role (Single Role)
- {role}

## 3. Target Locations
{locs_bullets}

## 4. Websites to Check
{sites_bullets}
"""
    with open(OPENCLAW_PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

ROLE_OPTIONS = [
    "Software Engineer",
    "Machine Learning Engineer",
    "AI Engineer",
    "Data Analyst",
    "Product Analyst",
    "Data Scientist",
    "Backend Engineer",
    "Frontend Engineer",
    "Type a Custom Job Role...",
]

LOCATION_OPTIONS = [
    "Remote",
    "Bengaluru",
    "Hyderabad",
    "Pune",
    "Gurugram",
    "Mumbai",
    "Chennai",
    "Delhi NCR",
]

PORTAL_OPTIONS = [
    "greenhouse",
    "workday",
    "lever",
]


def _interactive_single_select(title: str, subtitle: str, options: List[str], default_val: str = "") -> str:
    """
    Interactive terminal single-select menu with [✓] tick-box using Up/Down arrow keys
    and ENTER (via built-in Windows msvcrt). Enforces that ONLY ONE option can be selected.
    Falls back to numbered input if not running in an interactive console.
    """
    idx = 0
    for i, opt in enumerate(options):
        if opt.lower() == default_val.lower():
            idx = i
            break

    if os.name == "nt" and sys.stdin.isatty():
        import msvcrt

        num_lines = len(options) + 3
        first_draw = True

        while True:
            if not first_draw:
                sys.stdout.write(f"\033[{num_lines}A")
            first_draw = False

            sys.stdout.write(f"\033[K{title}\n")
            sys.stdout.write(f"\033[K  {subtitle}\n")
            for i, opt in enumerate(options):
                pointer = "❯" if i == idx else " "
                tick = "[✓]" if i == idx else "[ ]"
                sys.stdout.write(f"\033[K  {pointer} {tick} {opt}\n")
            sys.stdout.write("\033[K  (Use ↑/↓ Arrow Keys to move, press ENTER to confirm selection)\n")
            sys.stdout.flush()

            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                return options[idx]
            elif ch in ("\x00", "\xe0"):
                arrow = msvcrt.getwch()
                if arrow == "H":  # Up arrow
                    idx = (idx - 1) % len(options)
                elif arrow == "P":  # Down arrow
                    idx = (idx + 1) % len(options)
            elif ch.isdigit():
                n = int(ch)
                if 1 <= n <= len(options):
                    idx = n - 1

    # Fallback numbered prompt if non-interactive terminal
    print(f"\n{title}")
    print(f"  {subtitle}")
    for i, opt in enumerate(options, start=1):
        tick = "[✓]" if (i - 1) == idx else "[ ]"
        print(f"  {i}. {tick} {opt}")
    while True:
        raw = input(f"  Select ONE option (1-{len(options)}) [{idx + 1}]: ").strip()
        if not raw:
            return options[idx]
        if "," in raw or " " in raw:
            print("  [!] You can select ONLY ONE option. Please enter a single number.")
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  [!] Please enter a valid number between 1 and {len(options)}.")


def _interactive_multi_select(title: str, subtitle: str, options: List[str], defaults: List[str]) -> List[str]:
    """
    Interactive terminal multi-select menu with [✓] checkboxes using Up/Down arrow keys,
    SPACEBAR to toggle tick [✓], and ENTER to confirm.
    """
    selected_set = {i for i, opt in enumerate(options) if any(d.lower() == opt.lower() for d in defaults)}
    if not selected_set:
        selected_set = {0, 1}
    idx = 0

    if os.name == "nt" and sys.stdin.isatty():
        import msvcrt

        num_lines = len(options) + 3
        first_draw = True

        while True:
            if not first_draw:
                sys.stdout.write(f"\033[{num_lines}A")
            first_draw = False

            sys.stdout.write(f"\033[K{title}\n")
            sys.stdout.write(f"\033[K  {subtitle}\n")
            for i, opt in enumerate(options):
                pointer = "❯" if i == idx else " "
                tick = "[✓]" if i in selected_set else "[ ]"
                sys.stdout.write(f"\033[K  {pointer} {tick} {opt}\n")
            sys.stdout.write("\033[K  (Use ↑/↓ to move, SPACEBAR to tick/untick [✓], ENTER to confirm)\n")
            sys.stdout.flush()

            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                if selected_set:
                    return [options[i] for i in sorted(selected_set)]
            elif ch == " ":
                if idx in selected_set:
                    selected_set.remove(idx)
                else:
                    selected_set.add(idx)
            elif ch in ("\x00", "\xe0"):
                arrow = msvcrt.getwch()
                if arrow == "H":  # Up arrow
                    idx = (idx - 1) % len(options)
                elif arrow == "P":  # Down arrow
                    idx = (idx + 1) % len(options)

    # Fallback numbered prompt
    print(f"\n{title}")
    print(f"  {subtitle}")
    for i, opt in enumerate(options, start=1):
        tick = "[✓]" if (i - 1) in selected_set else "[ ]"
        print(f"  {i}. {tick} {opt}")
    default_str = ",".join(str(i + 1) for i in sorted(selected_set))
    raw = input(f"  Enter comma-separated numbers [{default_str}]: ").strip()
    if not raw:
        return [options[i] for i in sorted(selected_set)]
    chosen = []
    for p in raw.split(","):
        p = p.strip()
        if p.isdigit() and 1 <= int(p) <= len(options):
            val = options[int(p) - 1]
            if val not in chosen:
                chosen.append(val)
    return chosen or [options[i] for i in sorted(selected_set)]


def run_terminal_signup_wizard() -> None:
    """
    Interactive Terminal-Only Sign-Up & Preferences Wizard with live [✓] tick-boxes.
    """
    if os.name == "nt":
        os.system("")  # Enable ANSI escape sequences in Windows terminal

    init_db()
    cfg = load_preferences_config()
    user_cfg = cfg.get("user") or {}
    prefs_cfg = cfg.get("search_preferences") or {}
    sched_cfg = cfg.get("schedule") or {}

    print("\n" + "=" * 70)
    print("   PERSONAL AI JOB-SEARCH AGENT — TERMINAL SIGN-UP & SETUP")
    print("=" * 70)
    print("Configure your daily job alerts directly inside the terminal (No Website Needed).\n")

    # 1. Full Name
    default_name = user_cfg.get("name") or "Aryush Tripathi"
    name = input(f"1. Enter Full Name [{default_name}]: ").strip() or default_name

    # 2. Recipient Gmail Address
    default_email = user_cfg.get("email") or "22mm02002@iitbbs.ac.in"
    email = input(f"2. Enter Recipient Gmail Address [{default_email}]: ").strip() or default_email

    # 3. Gmail 16-Character App Password (or reuse existing sender key)
    existing_smtp_email = get_setting("SMTP_EMAIL", "")
    existing_app_pass = get_setting("SMTP_APP_PASSWORD", "")
    if existing_app_pass:
        print(f"\n   [Info] Pre-configured sender key ({existing_smtp_email}) is active.")
        print("   Press ENTER to reuse this sender key, or type your own 16-char App Password:")
        app_pass = input("3. Gmail 16-Character App Password [Keep Existing]: ").strip()
    else:
        print("\n   (Get your 16-char Gmail App Password at: https://myaccount.google.com/apppasswords)")
        app_pass = input("3. Enter Gmail 16-Character App Password: ").strip()

    if app_pass:
        clean_app_pass = re.sub(r"\s+", "", app_pass)
        set_settings({"SMTP_EMAIL": email, "SMTP_APP_PASSWORD": clean_app_pass})
    elif not existing_smtp_email:
        set_settings({"SMTP_EMAIL": email})

    print()
    # 4. Select Job Role (Single-Select Tick-Box)
    saved_roles = prefs_cfg.get("active_roles") or []
    default_role = saved_roles[0] if saved_roles else ""
    selected_role = _interactive_single_select(
        title="4. Select Target Job Role:",
        subtitle="NOTE: You can select ONLY ONE job role (1 role at a time).",
        options=ROLE_OPTIONS,
        default_val=default_role,
    )
    if selected_role == "Type a Custom Job Role...":
        custom_r = input("   Enter your custom job role (ONLY ONE role): ").strip()
        selected_role = custom_r.split(",")[0].strip() if custom_r else (default_role or ROLE_OPTIONS[0])

    print(f"   ✓ Selected Job Role: {selected_role}\n")

    # 5. Select Locations (Multi-Select Checkboxes with SPACEBAR)
    default_locs = prefs_cfg.get("locations") or ["Remote", "Bengaluru", "Hyderabad", "Gurugram", "Mumbai", "Pune"]
    selected_locations = _interactive_multi_select(
        title="5. Select Target Locations (including Remote):",
        subtitle="You can tick MULTIPLE locations using SPACEBAR, then press ENTER.",
        options=LOCATION_OPTIONS,
        defaults=default_locs,
    )
    print(f"   ✓ Selected Locations: {', '.join(selected_locations)}\n")

    # 6. Select Websites to Check (Multi-Select Checkboxes with SPACEBAR)
    default_sites = prefs_cfg.get("enabled_sources") or ["greenhouse", "workday", "lever"]
    selected_sites = _interactive_multi_select(
        title="6. Select Job Portals to Search:",
        subtitle="Tick the websites to check using SPACEBAR, then press ENTER.",
        options=PORTAL_OPTIONS,
        defaults=default_sites,
    )
    print(f"   ✓ Selected Portals: {', '.join(s.title() for s in selected_sites)}\n")

    # Fixed 11:00 AM daily schedule (not asked from the user)
    sched_time = "11:00"

    # Save to config/job_preferences.yaml
    cfg = update_preferences_config(
        name=name,
        email=email,
        roles=[selected_role],
        locations=selected_locations,
        sources=selected_sites,
    )
    if "schedule" not in cfg:
        cfg["schedule"] = {"timezone": "Asia/Kolkata"}
    cfg["schedule"]["daily_times"] = [sched_time]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

    # Save to dedicated per-user SQLite database
    user_db_path = save_user_profile_to_user_db(
        email=email,
        name=name,
        role=selected_role,
        locations=selected_locations,
        sites=selected_sites,
    )

    # Sync openclaw_agent/job_profile.md
    write_openclaw_profile_md(
        name=name,
        email=email,
        app_password=app_pass or existing_app_pass,
        role=selected_role,
        locations=selected_locations,
        sites=selected_sites,
    )

    # Install Windows Startup & Scheduled Task
    try:
        setup_windows_startup_and_tasks(schedule_time=sched_time)
    except Exception:
        pass

    print("\n" + "-" * 70)
    print("✓ Profile Saved Successfully!")
    print(f"  • Name:             {name}")
    print(f"  • Recipient Email:  {email}")
    print(f"  • Role (Single):    {selected_role}")
    print(f"  • Locations:        {', '.join(selected_locations)}")
    print(f"  • Portals:          {', '.join(s.title() for s in selected_sites)}")
    print(f"  • Daily Schedule:   {sched_time} IST (with automatic post-{sched_time} catch-up)")
    print(f"  • User Database:    {user_db_path}")
    print("-" * 70)

    run_now = input("\nWould you like to run a live scan & send a test email right now? (y/n) [n]: ").strip().lower()
    if run_now in ("y", "yes"):
        print("\nRunning live scan across selected portals...")
        summary = run_job_search_pipeline(send_email=True)
        print("\n" + format_plain_text_digest(summary))


if __name__ == "__main__":
    run_terminal_signup_wizard()
