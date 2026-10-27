import sqlite3
import hashlib
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs_watcher.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # Users table for Sign-Up and Login
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Subscriptions table: stores user's email alert subscription (only created when alert checkbox is ticked)
    # Default interval_minutes is 1440 (1 day / 24 hours)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            roles TEXT NOT NULL,          -- JSON list of target job titles
            location TEXT NOT NULL,       -- e.g. "Bengaluru"
            use_city_aliases INTEGER DEFAULT 1,
            platforms TEXT NOT NULL,      -- JSON list e.g. ["greenhouse", "lever", "workday"]
            interval_minutes INTEGER DEFAULT 1440,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            last_checked_at TEXT
        )
    """)

    # Discovered jobs table: deduplicates jobs per subscription so we only email NEW postings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discovered_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            job_hash TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            platform TEXT NOT NULL,
            location TEXT NOT NULL,
            url TEXT NOT NULL,
            snippet TEXT,
            search_query TEXT,
            posted_info TEXT,
            discovered_at TEXT NOT NULL,
            emailed INTEGER DEFAULT 0,
            UNIQUE(subscription_id, job_hash),
            FOREIGN KEY(subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
        )
    """)

    # Email logs table: stores sent & previewed email notifications
    cur.execute("""
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER,
            recipient_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            html_body TEXT NOT NULL,
            jobs_count INTEGER DEFAULT 0,
            status TEXT NOT NULL,         -- "sent_smtp", "preview_only", "failed"
            delivery_mode TEXT NOT NULL,  -- "gmail_smtp" or "in_app_preview"
            error_msg TEXT,
            sent_at TEXT NOT NULL
        )
    """)

    # App settings table: allows configuring API keys, LLM keys & SMTP via UI or .env
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# --- User Auth Functions ---

def register_user(name: str, email: str, password: str) -> Dict[str, Any]:
    clean_email = email.strip().lower()
    clean_name = name.strip() or clean_email.split("@")[0]
    pw_hash = _hash_password(password)
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
    existing = cur.fetchone()
    if existing:
        # Update name/password or log in directly if already registered
        cur.execute(
            "UPDATE users SET name = ?, password_hash = ? WHERE email = ?",
            (clean_name, pw_hash, clean_email),
        )
        conn.commit()
        cur.execute("SELECT id, name, email, created_at FROM users WHERE email = ?", (clean_email,))
        row = cur.fetchone()
        conn.close()
        return dict(row)

    cur.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (clean_name, clean_email, pw_hash, now),
    )
    user_id = cur.lastrowid
    conn.commit()
    cur.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row)


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    clean_email = email.strip().lower()
    pw_hash = _hash_password(password)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    if row["password_hash"] != pw_hash:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


# --- Settings Functions ---

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row and row["value"] != "":
        return row["value"]
    return os.environ.get(key, default)


def set_settings(settings_dict: Dict[str, str]) -> None:
    conn = get_connection()
    cur = conn.cursor()
    for k, v in settings_dict.items():
        if v is not None:
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, str(v).strip()),
            )
    conn.commit()
    conn.close()


def get_all_settings() -> Dict[str, str]:
    keys = [
        "SEARCH_PROVIDER",
        "LLM_PROVIDER",          # "gemini", "openai", "groq", or "auto"
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "SMTP_EMAIL",
        "SMTP_APP_PASSWORD",
        "SMTP_HOST",
        "SMTP_PORT",
    ]
    result = {}
    for k in keys:
        result[k] = get_setting(k, "")
    if not result["SEARCH_PROVIDER"]:
        result["SEARCH_PROVIDER"] = "auto"
    if not result["LLM_PROVIDER"]:
        result["LLM_PROVIDER"] = "auto"
    if not result["SMTP_HOST"]:
        result["SMTP_HOST"] = "smtp.gmail.com"
    if not result["SMTP_PORT"]:
        result["SMTP_PORT"] = "587"
    return result


# --- Subscription & Jobs Functions ---

def create_subscription(
    email: str,
    roles: List[str],
    location: str,
    platforms: List[str],
    interval_minutes: int = 1440,
    use_city_aliases: bool = True,
) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO subscriptions (email, roles, location, use_city_aliases, platforms, interval_minutes, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            email.strip().lower(),
            json.dumps([r.strip() for r in roles if r.strip()]),
            location.strip(),
            1 if use_city_aliases else 0,
            json.dumps([p.strip().lower() for p in platforms if p.strip()]),
            max(1, int(interval_minutes)),
            now,
        ),
    )
    sub_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_subscription(sub_id)


def get_subscription(sub_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_subscription(row) if row else None


def list_subscriptions(email: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    if email:
        cur.execute("SELECT * FROM subscriptions WHERE lower(email) = ? ORDER BY id DESC", (email.strip().lower(),))
    else:
        cur.execute("SELECT * FROM subscriptions ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_subscription(r) for r in rows]


def toggle_subscription(sub_id: int, is_active: bool) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE subscriptions SET is_active = ? WHERE id = ?", (1 if is_active else 0, sub_id))
    conn.commit()
    conn.close()
    return get_subscription(sub_id)


def delete_subscription(sub_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM discovered_jobs WHERE subscription_id = ?", (sub_id,))
    cur.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def update_subscription_last_checked(sub_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("UPDATE subscriptions SET last_checked_at = ? WHERE id = ?", (now, sub_id))
    conn.commit()
    conn.close()


def save_discovered_jobs(sub_id: int, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    new_jobs = []

    for job in jobs:
        job_hash = job["job_hash"]
        cur.execute(
            "SELECT id FROM discovered_jobs WHERE subscription_id = ? AND job_hash = ?",
            (sub_id, job_hash),
        )
        if cur.fetchone() is None:
            cur.execute(
                """
                INSERT INTO discovered_jobs (
                    subscription_id, job_hash, title, company, platform,
                    location, url, snippet, search_query, posted_info, discovered_at, emailed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    sub_id,
                    job_hash,
                    job.get("title", "Untitled Role"),
                    job.get("company", "Company"),
                    job.get("platform", "greenhouse"),
                    job.get("location", ""),
                    job.get("url", ""),
                    job.get("snippet", ""),
                    job.get("search_query", ""),
                    job.get("posted_info", "Recent"),
                    now,
                ),
            )
            job_copy = dict(job)
            job_copy["id"] = cur.lastrowid
            job_copy["subscription_id"] = sub_id
            job_copy["discovered_at"] = now
            new_jobs.append(job_copy)

    conn.commit()
    conn.close()
    return new_jobs


def mark_jobs_emailed(job_ids: List[int]) -> None:
    if not job_ids:
        return
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(job_ids))
    cur.execute(f"UPDATE discovered_jobs SET emailed = 1 WHERE id IN ({placeholders})", job_ids)
    conn.commit()
    conn.close()


def list_discovered_jobs(
    subscription_id: Optional[int] = None,
    platform: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM discovered_jobs WHERE 1=1"
    params: List[Any] = []
    if subscription_id is not None:
        query += " AND subscription_id = ?"
        params.append(subscription_id)
    if platform:
        query += " AND platform = ?"
        params.append(platform.lower())
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_email(
    subscription_id: Optional[int],
    recipient_email: str,
    subject: str,
    html_body: str,
    jobs_count: int,
    status: str,
    delivery_mode: str,
    error_msg: str = "",
) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO email_logs (
            subscription_id, recipient_email, subject, html_body,
            jobs_count, status, delivery_mode, error_msg, sent_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subscription_id,
            recipient_email,
            subject,
            html_body,
            jobs_count,
            status,
            delivery_mode,
            error_msg,
            now,
        ),
    )
    log_id = cur.lastrowid
    conn.commit()
    cur.execute("SELECT * FROM email_logs WHERE id = ?", (log_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row)


def list_email_logs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM email_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _row_to_subscription(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["roles"] = json.loads(d.get("roles") or "[]")
    d["platforms"] = json.loads(d.get("platforms") or "[]")
    d["use_city_aliases"] = bool(d.get("use_city_aliases", 1))
    d["is_active"] = bool(d.get("is_active", 1))
    return d
