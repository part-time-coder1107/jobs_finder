import argparse
import json
import os
import socket
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
import yaml
from dotenv import load_dotenv

from src.collectors import COLLECTOR_REGISTRY
from src.normalizer import normalize_raw_jobs
from src.job_matcher import filter_and_rank_jobs
from src.database import (
    reconcile_and_store_jobs,
    record_sent_notifications,
    has_run_today,
    record_daily_run,
    save_user_profile_to_user_db,
    get_user_profile_from_user_db,
)
from src.email_notifier import format_plain_text_digest, send_consolidated_digest
from src.models import RawJob, ScanSummary

load_dotenv()


def is_internet_connected() -> bool:
    """
    Verifies both DNS resolution (getaddrinfo) and outbound TCP connectivity to
    both Gmail SMTP (smtp.gmail.com:587) and Greenhouse API (boards-api.greenhouse.io:443)
    so the agent never runs while Wi-Fi DNS is still initializing after boot.
    """
    try:
        with socket.create_connection(("smtp.gmail.com", 587), timeout=4):
            pass
        with socket.create_connection(("boards-api.greenhouse.io", 443), timeout=4):
            return True
    except OSError:
        return False


def wait_for_internet_connection(max_wait_seconds: int = 1800) -> bool:
    """
    When the laptop turns on after 12:00 PM, Wi-Fi may take 10-60 seconds to connect.
    This function waits until the internet connection is active before starting the scan.
    """
    start = time.time()
    while time.time() - start < max_wait_seconds:
        if is_internet_connected():
            return True
        time.sleep(5)
    return is_internet_connected()

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "job_preferences.yaml",
)
LOCK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "scan.lock",
)


def _acquire_scan_lock(max_age_seconds: int = 300) -> bool:
    """
    Prevents duplicate concurrent runs if Windows Task Scheduler (--catch-up)
    and the Startup Watcher (--schedule) trigger at the exact same moment on wake-up.
    """
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    if os.path.exists(LOCK_PATH):
        try:
            age = time.time() - os.path.getmtime(LOCK_PATH)
            if age < max_age_seconds:
                return False
            os.remove(LOCK_PATH)
        except OSError:
            pass
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except OSError:
        return False


def _release_scan_lock() -> None:
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except OSError:
        pass


def load_preferences_config(config_path: str = CONFIG_PATH) -> Dict[str, Any]:
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def update_preferences_config(
    name: Optional[str] = None,
    email: Optional[str] = None,
    roles: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    config_path: str = CONFIG_PATH,
) -> Dict[str, Any]:
    """
    Updates config/job_preferences.yaml and the user's SQLite DB when preferences are saved in the terminal.
    """
    cfg = load_preferences_config(config_path)
    if "user" not in cfg:
        cfg["user"] = {}
    if "search_preferences" not in cfg:
        cfg["search_preferences"] = {}
    if "schedule" not in cfg:
        cfg["schedule"] = {"timezone": "Asia/Kolkata"}
    cfg["schedule"]["daily_times"] = ["11:00"]

    if name:
        cfg["user"]["name"] = name.strip()
    if email:
        cfg["user"]["email"] = email.strip()
    if roles:
        cfg["search_preferences"]["active_roles"] = [r.strip() for r in roles if r.strip()]
    cfg["search_preferences"].pop("experience", None)
    if locations:
        cfg["search_preferences"]["locations"] = [loc.strip() for loc in locations if loc.strip()]
    if sources:
        cfg["search_preferences"]["enabled_sources"] = [s.strip().lower() for s in sources if s.strip()]

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

    user_email = (cfg.get("user") or {}).get("email") or ""
    user_name = (cfg.get("user") or {}).get("name") or ""
    active_roles = (cfg.get("search_preferences") or {}).get("active_roles") or []
    active_locs = (cfg.get("search_preferences") or {}).get("locations") or []
    active_sources = (cfg.get("search_preferences") or {}).get("enabled_sources") or []
    if user_email and active_roles:
        save_user_profile_to_user_db(
            email=user_email,
            name=user_name,
            role=active_roles[0],
            locations=active_locs,
            sites=active_sources,
        )

    return cfg


def run_job_search_pipeline(
    override_roles: Optional[List[str]] = None,
    override_locations: Optional[List[str]] = None,
    override_sources: Optional[List[str]] = None,
    override_email: Optional[str] = None,
    override_name: Optional[str] = None,
    send_email: bool = True,
) -> ScanSummary:
    """
    Executes the full 6-component Personal AI Job-Search Engine pipeline:
      1. Load Profile & Preferences (dynamically from user preference in config & user DB)
      2. Collect jobs from enabled collectors (Greenhouse, Lever, Workday)
      3. Normalize into canonical JobPosting objects
      4. Filter & Rank (Stage 1 Rule Filter + Stage 2 Skill Scoring + Recency sort)
      5. Reconcile against per-user SQLite DB (Identify new discoveries vs previously reported)
      6. Send consolidated Gmail report & mark notified
    """
    cfg = load_preferences_config()
    user_cfg = cfg.get("user") or {}
    prefs_cfg = cfg.get("search_preferences") or {}

    recipient_email = (override_email or user_cfg.get("email") or "").strip()
    db_profile = get_user_profile_from_user_db(recipient_email) if recipient_email else {}

    user_name = override_name or user_cfg.get("name") or db_profile.get("name") or "User"
    db_role = [db_profile["role"]] if db_profile.get("role") else []
    roles = override_roles or prefs_cfg.get("active_roles") or db_role
    locations = override_locations or prefs_cfg.get("locations") or db_profile.get("locations") or []
    sources = override_sources or prefs_cfg.get("enabled_sources") or db_profile.get("sites") or ["greenhouse", "workday", "lever"]

    # Step 2: Run enabled collectors
    raw_collected: List[RawJob] = []
    for src_name in sources:
        key = src_name.strip().lower()
        collector_cls = COLLECTOR_REGISTRY.get(key)
        if not collector_cls:
            continue
        collector = collector_cls()
        try:
            jobs_from_source = collector.collect(roles=roles, locations=locations, config=cfg)
            raw_collected.extend(jobs_from_source)
        except Exception:
            continue

    # Step 3: Normalize
    normalized_jobs = normalize_raw_jobs(raw_collected)

    # Step 4: Two-Stage Filter & Rank (Most Recent Posted Date first)
    matched_ranked_jobs = filter_and_rank_jobs(
        jobs=normalized_jobs,
        roles=roles,
        locations=locations,
        config=cfg,
    )

    # Step 5: Reconcile with SQLite (`jobs` & `notifications` tables)
    new_jobs, previously_reported_excluded = reconcile_and_store_jobs(
        candidate_jobs=matched_ranked_jobs,
        recipient_email=recipient_email,
    )

    strong_matches = sum(1 for j in new_jobs if j.match_score >= 80)
    verification_needed = sum(
        1 for j in new_jobs if "verification" in j.eligibility.lower()
    )

    summary = ScanSummary(
        user_name=user_name,
        recipient_email=recipient_email,
        scan_time=datetime.now().isoformat(timespec="seconds"),
        total_collected=len(normalized_jobs),
        new_jobs_discovered=len(new_jobs),
        strong_matches_count=strong_matches,
        verification_needed_count=verification_needed,
        previously_reported_excluded=previously_reported_excluded,
        ranked_new_jobs=new_jobs,
    )

    # Step 6: Send Consolidated Report
    # Guard: if 0 total jobs were collected across all boards (e.g. Wi-Fi dropped mid-scan
    # right after wakeup), do NOT send a false empty email or mark today's run complete,
    # so the watcher automatically retries once the connection is stable.
    if not normalized_jobs:
        return summary

    email_succeeded = False
    if send_email:
        digest_result = send_consolidated_digest(summary)
        if digest_result.get("status") == "sent_smtp":
            email_succeeded = True
            if new_jobs:
                record_sent_notifications(new_jobs, recipient_email=recipient_email)

    # ONLY mark today's daily run complete if the email was actually delivered via SMTP!
    target_times = (cfg.get("schedule") or {}).get("daily_times") or ["11:00"]
    scheduled_hm = target_times[0]
    if email_succeeded and datetime.now().strftime("%H:%M") >= scheduled_hm:
        record_daily_run(recipient_email, new_jobs_sent=len(new_jobs))

    return summary


def run_catch_up_if_missed() -> Optional[ScanSummary]:
    """
    Natural catch-up check:
    Reads the configured daily time from config/job_preferences.yaml.
    If the current time is >= that scheduled time AND today's scan has not run yet,
    waits for an active internet connection and runs the scan once for today.
    """
    cfg = load_preferences_config()
    recipient_email = ((cfg.get("user") or {}).get("email") or "22mm02002@iitbbs.ac.in").strip()
    target_times = (cfg.get("schedule") or {}).get("daily_times") or ["11:00"]
    scheduled_hm = target_times[0]

    current_hm = datetime.now().strftime("%H:%M")
    if current_hm < scheduled_hm or has_run_today(recipient_email, scheduled_hm):
        return None

    print(f"[{datetime.now().isoformat(timespec='seconds')}] Scheduled time ({scheduled_hm}) passed and not yet run today. Waiting for internet...")
    if not wait_for_internet_connection(max_wait_seconds=3600):
        print("[Catch-Up] No internet connection detected within timeout.")
        return None

    if has_run_today(recipient_email, scheduled_hm) or not _acquire_scan_lock():
        return None

    try:
        print(f"[{datetime.now().isoformat(timespec='seconds')}] Internet connected! Running today's scheduled scan...")
        summary = run_job_search_pipeline(send_email=True)
        print(format_plain_text_digest(summary))
        return summary
    finally:
        _release_scan_lock()


def run_daily_10am_10pm_scheduler() -> None:
    """
    Natural daily scheduler loop:
    Reads `daily_times[0]` from config/job_preferences.yaml.
    As soon as `current_hm >= scheduled_hm` AND `not has_run_today(recipient_email, scheduled_hm)`
    AND the laptop is connected to the internet, it runs the daily scan once and
    records today's completion in the database only when the email succeeds.
    """
    cfg = load_preferences_config()
    target_times = (cfg.get("schedule") or {}).get("daily_times") or ["11:00"]
    print(f"[Scheduler] Personal AI Job Agent active. Configured daily time: {target_times[0]}")

    while True:
        cfg = load_preferences_config()
        target_times = (cfg.get("schedule") or {}).get("daily_times") or ["11:00"]
        scheduled_hm = target_times[0]
        recipient_email = ((cfg.get("user") or {}).get("email") or "22mm02002@iitbbs.ac.in").strip()

        now = datetime.now()
        current_hm = now.strftime("%H:%M")

        if current_hm >= scheduled_hm and not has_run_today(recipient_email, scheduled_hm):
            if is_internet_connected() and _acquire_scan_lock():
                try:
                    print(f"\n[{now.isoformat(timespec='seconds')}] Running daily scheduled scan (target: {scheduled_hm})...")
                    summary = run_job_search_pipeline(send_email=True)
                    print(format_plain_text_digest(summary))
                finally:
                    _release_scan_lock()

        time.sleep(20)


def main():
    parser = argparse.ArgumentParser(
        description="Personal AI Job-Search Agent (Greenhouse, Lever, Workday)"
    )
    parser.add_argument("--setup", action="store_true", help="Run interactive terminal Sign-Up & Preferences wizard (No Web UI needed)")
    parser.add_argument("--run-once", action="store_true", help="Run a single scan immediately")
    parser.add_argument("--catch-up", action="store_true", help="Wait for internet and run today's scheduled scan if missed")
    parser.add_argument("--schedule", action="store_true", help="Run daily scheduler with automatic catch-up")
    parser.add_argument("--json", action="store_true", help="Output structured JSON (for OpenClaw integration)")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email during this run")
    parser.add_argument("--role", type=str, help="Set/override job role preference to search")
    parser.add_argument("--locations", type=str, help="Comma-separated locations (e.g. 'Bengaluru, Remote')")
    parser.add_argument("--sources", type=str, help="Comma-separated platforms (e.g. 'greenhouse, workday, lever')")
    args = parser.parse_args()

    if args.setup:
        from setup_agent import run_terminal_signup_wizard

        run_terminal_signup_wizard()
        return

    override_roles = [r.strip() for r in args.role.split(",") if r.strip()] if args.role else None
    override_locs = [x.strip() for x in args.locations.split(",") if x.strip()] if args.locations else None
    override_sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()] if args.sources else None

    if override_roles or override_locs or override_sources:
        update_preferences_config(
            roles=override_roles,
            locations=override_locs,
            sources=override_sources,
        )

    if args.schedule:
        run_daily_10am_10pm_scheduler()
        return

    if args.catch_up:
        run_catch_up_if_missed()
        return

    wait_for_internet_connection(max_wait_seconds=300)
    summary = run_job_search_pipeline(
        override_roles=override_roles,
        override_locations=override_locs,
        override_sources=override_sources,
        send_email=not args.no_email,
    )

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(format_plain_text_digest(summary))


if __name__ == "__main__":
    main()
