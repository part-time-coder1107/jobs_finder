import os
import re
import subprocess
import sys
from typing import Optional
import yaml

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable
CONFIG_PATH = os.path.join(WORKSPACE_DIR, "config", "job_preferences.yaml")


def normalize_schedule_time(raw_time: str) -> str:
    """
    Converts user-entered time strings such as '11:00', '9:30 AM', '2:15 PM',
    '11 am', '6 pm', or '18:30' into 24-hour 'HH:MM' format for Windows Task Scheduler.
    """
    s = (raw_time or "").strip()
    if not s:
        return "11:00"

    # Extract leading HH:MM if formatted like '11:00 (11:00 AM)'
    m_prefix = re.match(r"^(\d{1,2}:\d{2})\s*\(", s)
    if m_prefix:
        s = m_prefix.group(1)

    m_ampm = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", s.lower())
    if m_ampm:
        hr = int(m_ampm.group(1))
        mn = int(m_ampm.group(2) or 0)
        meridiem = m_ampm.group(3)
        if meridiem == "pm" and hr < 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        hr = max(0, min(23, hr))
        mn = max(0, min(59, mn))
        return f"{hr:02d}:{mn:02d}"

    m_24 = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m_24:
        hr = max(0, min(23, int(m_24.group(1))))
        mn = max(0, min(59, int(m_24.group(2))))
        return f"{hr:02d}:{mn:02d}"

    m_hr_only = re.match(r"^(\d{1,2})$", s)
    if m_hr_only:
        hr = max(0, min(23, int(m_hr_only.group(1))))
        return f"{hr:02d}:00"

    return "11:00"


def _get_configured_time() -> str:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            times = (cfg.get("schedule") or {}).get("daily_times") or []
            if times:
                return normalize_schedule_time(str(times[0]))
        except Exception:
            pass
    return "11:00"


def setup_windows_startup_and_tasks(schedule_time: Optional[str] = None) -> str:
    """
    Dynamically configures Windows Task Scheduler and the Windows Startup watcher
    for the exact `schedule_time` (HH:MM) selected by the user.
    """
    final_time = normalize_schedule_time(schedule_time) if schedule_time else _get_configured_time()

    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )
    os.makedirs(startup_dir, exist_ok=True)
    vbs_path = os.path.join(startup_dir, "JobAgent_12PM_Watcher.vbs")

    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{WORKSPACE_DIR}"
WshShell.Run """{PYTHON_EXE}"" -m src.main --schedule", 0, False
'''
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    # Also ensure the background watcher is running immediately in the current session
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\' AND CommandLine LIKE \'%src.main --schedule%\'" | Invoke-CimMethod -MethodName Terminate -ErrorAction SilentlyContinue',
            ],
            capture_output=True,
            text=True,
        )
        subprocess.Popen(["wscript.exe", "//B", vbs_path], close_fds=True)
    except Exception:
        pass

    cmd_str = f'cmd /c cd /d "{WORKSPACE_DIR}" && "{PYTHON_EXE}" -m src.main --catch-up'
    for task_name in ("JobAgent_12PM_Noon", "JobAgent_Daily"):
        subprocess.run(
            [
                "schtasks",
                "/Create",
                "/SC",
                "DAILY",
                "/TN",
                task_name,
                "/TR",
                cmd_str,
                "/ST",
                final_time,
                "/F",
            ],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'Set-ScheduledTask -TaskName "{task_name}" -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)',
            ],
            capture_output=True,
            text=True,
        )

    return final_time


if __name__ == "__main__":
    arg_time = sys.argv[1] if len(sys.argv) > 1 else None
    configured = setup_windows_startup_and_tasks(arg_time)
    print(f"Windows Task Scheduler & Startup Watcher configured for {configured} daily.")
