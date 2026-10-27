import json
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime
from typing import List, Tuple, Dict, Any
from src.models import NormalizedJob

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DB_PATH = os.path.join(BASE_DIR, "jobs_watcher.db")
USER_DBS_DIR = os.path.join(BASE_DIR, "data", "user_dbs")


def get_user_db_path(recipient_email: str) -> str:
    """
    Returns the path to the dedicated, isolated SQLite database file linked
    specifically to `recipient_email` (e.g. data/user_dbs/22mm02002_at_iitbbs.ac.in.db).
    Each user has their own separate database of sent jobs and preferences.
    """
    os.makedirs(USER_DBS_DIR, exist_ok=True)
    clean = (recipient_email or "default_user").strip().lower()
    safe_name = clean.replace("@", "_at_")
    safe_name = re.sub(r"[^a-z0-9._-]", "_", safe_name)
    return os.path.join(USER_DBS_DIR, f"{safe_name}.db")


def _compute_strict_keys(job: NormalizedJob) -> Tuple[str, str, str]:
    """
    Computes the 3 strict deduplication keys for a job:
      1. job_id: canonical ID
      2. canonical_url: normalized scheme://netloc/path (plus gh_jid if present)
      3. title_company_key: normalized 'company|title' fingerprint
    If ANY of these 3 keys matches a previously emailed job in the user's database,
    the job is strictly excluded from future emails.
    """
    try:
        p = urllib.parse.urlparse(job.job_url.strip())
        qs = urllib.parse.parse_qs(p.query)
        gh_jid = qs.get("gh_jid", [""])[0]
        canonical_url = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/").lower()
        if gh_jid:
            canonical_url = f"{canonical_url}?gh_jid={gh_jid.lower()}"
    except Exception:
        canonical_url = job.job_url.strip().lower()

    norm_comp = re.sub(r"\s+", " ", job.company.strip().lower())
    norm_title = re.sub(r"\s+", " ", job.title.strip().lower())
    title_company_key = f"{norm_comp}|{norm_title}"

    return job.job_id, canonical_url, title_company_key


def init_user_db(recipient_email: str) -> str:
    """
    Initializes the dedicated per-user SQLite database linked to `recipient_email`.
    """
    user_db_path = get_user_db_path(recipient_email)
    conn = sqlite3.connect(user_db_path, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            email TEXT PRIMARY KEY,
            name TEXT,
            role TEXT,
            experience TEXT,
            locations TEXT,
            sites TEXT,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sent_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_email TEXT NOT NULL,
            job_id TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            title_company_key TEXT NOT NULL,
            platform TEXT,
            company TEXT,
            title TEXT,
            location TEXT,
            experience_level TEXT,
            posted_at TEXT,
            job_url TEXT,
            sent_at TEXT NOT NULL,
            run_slot TEXT,
            UNIQUE(job_id),
            UNIQUE(canonical_url),
            UNIQUE(title_company_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_runs (
            run_date TEXT PRIMARY KEY,
            recipient_email TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            new_jobs_sent INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    return user_db_path


def get_user_profile_from_user_db(email: str) -> Dict[str, Any]:
    """
    Loads the user's saved preferences (name, role, locations, sites) from their
    dedicated per-user SQLite database if present.
    """
    if not email or not email.strip():
        return {}
    user_db_path = init_user_db(email)
    conn = sqlite3.connect(user_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT email, name, role, locations, sites, updated_at FROM user_profile WHERE email = ?",
        (email.strip().lower(),),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    d = dict(row)
    try:
        d["locations"] = json.loads(d.get("locations") or "[]")
    except Exception:
        d["locations"] = []
    try:
        d["sites"] = json.loads(d.get("sites") or "[]")
    except Exception:
        d["sites"] = []
    return d


def has_run_today(recipient_email: str, scheduled_hm: str = "11:00") -> bool:
    """
    Checks the user's dedicated database to see if today's scheduled daily scan
    has already been completed at or after `scheduled_hm` today.
    """
    user_db_path = init_user_db(recipient_email)
    conn = sqlite3.connect(user_db_path, check_same_thread=False)
    cur = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT completed_at FROM daily_runs WHERE run_date = ?", (today_str,))
    row = cur.fetchone()
    conn.close()
    if row is None or not row[0]:
        return False
    completed_hm = str(row[0])[11:16]
    return completed_hm >= scheduled_hm


def record_daily_run(recipient_email: str, new_jobs_sent: int = 0) -> None:
    """
    Marks today's daily scan (YYYY-MM-DD) as completed in the user's dedicated database
    so the agent runs naturally once per day at or after the configured daily time.
    """
    user_db_path = init_user_db(recipient_email)
    conn = sqlite3.connect(user_db_path, check_same_thread=False)
    cur = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_iso = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO daily_runs (run_date, recipient_email, completed_at, new_jobs_sent)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(run_date) DO UPDATE SET
            completed_at = excluded.completed_at,
            new_jobs_sent = excluded.new_jobs_sent
        """,
        (today_str, recipient_email.strip().lower(), now_iso, new_jobs_sent),
    )
    conn.commit()
    conn.close()


def save_user_profile_to_user_db(
    email: str,
    name: str,
    role: str,
    locations: List[str],
    sites: List[str],
) -> str:
    """
    Saves the user's preferences into their dedicated per-user SQLite database.
    """
    user_db_path = init_user_db(email)
    conn = sqlite3.connect(user_db_path, check_same_thread=False)
    cur = conn.cursor()
    now_iso = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO user_profile (email, name, role, locations, sites, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name = excluded.name,
            role = excluded.role,
            locations = excluded.locations,
            sites = excluded.sites,
            updated_at = excluded.updated_at
        """,
        (
            email.strip().lower(),
            name.strip(),
            role.strip(),
            json.dumps(locations),
            json.dumps(sites),
            now_iso,
        ),
    )
    conn.commit()
    conn.close()
    return user_db_path


def get_db_connection(db_path: str = CORE_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_core_db(db_path: str = CORE_DB_PATH) -> None:
    """
    Initializes the `jobs` table and `notifications` table for the standalone
    Python Core Job-Search Engine.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT,
            job_url TEXT NOT NULL,
            description TEXT,
            posted_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            match_score REAL DEFAULT 0,
            role_category TEXT,
            experience_level TEXT,
            eligibility TEXT,
            matching_skills TEXT,
            why_it_matches TEXT,
            status TEXT DEFAULT 'active'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            run_slot TEXT,
            UNIQUE(job_id, recipient_email)
        )
    """)

    conn.commit()
    conn.close()


def reconcile_and_store_jobs(
    candidate_jobs: List[NormalizedJob],
    recipient_email: str,
    db_path: str = CORE_DB_PATH,
) -> Tuple[List[NormalizedJob], int]:
    """
    Compares candidate_jobs against:
      1. The user's dedicated separate SQLite database (`data/user_dbs/<email>.db`)
         using strict 3-key matching (`job_id`, `canonical_url`, and `company|title`).
      2. The central `jobs` and `notifications` tables.
    Returns (unreported_new_jobs, previously_reported_excluded_count) so a job
    already sent to `recipient_email` NEVER appears in their next email.
    """
    init_core_db(db_path)
    user_db_path = init_user_db(recipient_email)

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    uconn = sqlite3.connect(user_db_path, check_same_thread=False)
    ucur = uconn.cursor()

    now_iso = datetime.now().isoformat(timespec="seconds")
    clean_email = recipient_email.strip().lower()

    new_unreported_jobs: List[NormalizedJob] = []
    excluded_already_reported = 0
    seen_in_batch_keys = set()

    for job in candidate_jobs:
        cur.execute("SELECT job_id, first_seen_at FROM jobs WHERE job_id = ?", (job.job_id,))
        existing = cur.fetchone()

        if existing is None:
            cur.execute(
                """
                INSERT INTO jobs (
                    job_id, platform, company, title, location, job_url, description,
                    posted_at, first_seen_at, last_seen_at, match_score, role_category,
                    experience_level, eligibility, matching_skills, why_it_matches, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    job.job_id,
                    job.platform,
                    job.company,
                    job.title,
                    job.location,
                    job.job_url,
                    job.description,
                    job.posted_at,
                    job.first_seen_at,
                    now_iso,
                    job.match_score,
                    job.role_category,
                    job.experience_level,
                    job.eligibility,
                    json.dumps(job.matching_skills),
                    job.why_it_matches,
                ),
            )
        else:
            job.first_seen_at = existing["first_seen_at"]
            job.last_seen_at = now_iso
            cur.execute(
                """
                UPDATE jobs
                SET last_seen_at = ?, match_score = ?, eligibility = ?, why_it_matches = ?, status = 'active'
                WHERE job_id = ?
                """,
                (now_iso, job.match_score, job.eligibility, job.why_it_matches, job.job_id),
            )

        # Strict 3-key check against this user's dedicated database (sent_jobs)
        jid, canonical_url, title_company_key = _compute_strict_keys(job)

        if title_company_key in seen_in_batch_keys or canonical_url in seen_in_batch_keys:
            excluded_already_reported += 1
            continue

        ucur.execute(
            """
            SELECT id FROM sent_jobs
            WHERE job_id = ? OR canonical_url = ? OR title_company_key = ?
            """,
            (jid, canonical_url, title_company_key),
        )
        already_in_user_db = ucur.fetchone() is not None

        cur.execute(
            "SELECT id FROM notifications WHERE job_id = ? AND recipient_email = ?",
            (job.job_id, clean_email),
        )
        already_in_core_db = cur.fetchone() is not None

        if already_in_user_db or already_in_core_db:
            excluded_already_reported += 1
        else:
            seen_in_batch_keys.add(title_company_key)
            seen_in_batch_keys.add(canonical_url)
            new_unreported_jobs.append(job)

    conn.commit()
    conn.close()
    uconn.close()
    return new_unreported_jobs, excluded_already_reported


def record_sent_notifications(
    jobs: List[NormalizedJob],
    recipient_email: str,
    run_slot: str = "",
    db_path: str = CORE_DB_PATH,
) -> None:
    """
    Records all sent jobs into both:
      1. The user's dedicated SQLite database (`data/user_dbs/<email>.db` -> `sent_jobs`)
      2. The central `notifications` table
    so that none of these jobs can ever be sent again to `recipient_email`.
    """
    if not jobs:
        return
    init_core_db(db_path)
    user_db_path = init_user_db(recipient_email)

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    uconn = sqlite3.connect(user_db_path, check_same_thread=False)
    ucur = uconn.cursor()

    now_iso = datetime.now().isoformat(timespec="seconds")
    clean_email = recipient_email.strip().lower()
    slot = run_slot or datetime.now().strftime("%Y-%m-%d_%H%M")

    for j in jobs:
        jid, canonical_url, title_company_key = _compute_strict_keys(j)
        cur.execute(
            """
            INSERT OR IGNORE INTO notifications (job_id, recipient_email, sent_at, run_slot)
            VALUES (?, ?, ?, ?)
            """,
            (j.job_id, clean_email, now_iso, slot),
        )
        ucur.execute(
            """
            INSERT OR IGNORE INTO sent_jobs (
                recipient_email, job_id, canonical_url, title_company_key,
                platform, company, title, location, experience_level, posted_at, job_url, sent_at, run_slot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_email,
                jid,
                canonical_url,
                title_company_key,
                j.platform,
                j.company,
                j.title,
                j.location,
                j.experience_level,
                j.posted_at,
                j.job_url,
                now_iso,
                slot,
            ),
        )

    conn.commit()
    conn.close()
    uconn.commit()
    uconn.close()


def list_stored_jobs(limit: int = 100, db_path: str = CORE_DB_PATH) -> List[Dict[str, Any]]:
    init_core_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs ORDER BY match_score DESC, last_seen_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["matching_skills"] = json.loads(d.get("matching_skills") or "[]")
        except Exception:
            d["matching_skills"] = []
        results.append(d)
    return results
