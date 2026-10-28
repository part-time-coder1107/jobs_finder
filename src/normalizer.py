import hashlib
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict
from src.models import RawJob, NormalizedJob

CITY_ALIASES: Dict[str, List[str]] = {
    "bengaluru": ["bengaluru", "bangalore"],
    "bangalore": ["bangalore", "bengaluru"],
    "gurugram": ["gurugram", "gurgaon"],
    "gurgaon": ["gurgaon", "gurugram"],
    "mumbai": ["mumbai", "navi mumbai", "bombay"],
    "delhi": ["delhi", "new delhi", "delhi ncr", "noida", "gurugram", "gurgaon"],
    "delhi ncr": ["delhi", "new delhi", "delhi ncr", "noida", "gurugram", "gurgaon"],
    "noida": ["noida", "greater noida", "delhi ncr"],
    "hyderabad": ["hyderabad", "secunderabad"],
    "chennai": ["chennai", "madras"],
    "pune": ["pune"],
    "remote": ["remote", "remote - india", "remote, india", "work from home", "anywhere"],
}


def expand_location_aliases(locations: List[str]) -> List[str]:
    expanded: List[str] = []
    for loc in locations:
        clean = loc.strip().lower()
        if not clean:
            continue
        variants = CITY_ALIASES.get(clean, [clean])
        for v in variants:
            if v not in expanded:
                expanded.append(v)
    return expanded


def compute_canonical_job_id(raw: RawJob) -> str:
    """
    Constructs a deterministic unique job_id from the platform's external_id or
    normalized (platform + canonical URL + company + title).
    """
    if raw.external_id:
        base = f"{raw.platform.lower()}|{raw.external_id.strip().lower()}"
    else:
        try:
            p = urllib.parse.urlparse(raw.job_url)
            canonical_url = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/").lower()
        except Exception:
            canonical_url = raw.job_url.strip().lower()
        base = f"{raw.platform.lower()}|{canonical_url}|{raw.company.strip().lower()}|{raw.title.strip().lower()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def standardize_posted_date(raw_posted: str) -> str:
    """
    Converts relative date strings (like Workday's 'Posted Today', 'Posted Yesterday',
    'Posted 5 Days Ago', 'Posted 30+ Days Ago') and ISO timestamps into 'YYYY-MM-DD'.
    """
    s = (raw_posted or "").strip()
    if not s:
        return "Unknown"

    low = s.lower()
    today = datetime.now().date()

    if "today" in low or "just posted" in low:
        return today.strftime("%Y-%m-%d")
    if "yesterday" in low:
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")

    if "30+" in low or "30 +" in low:
        return (today - timedelta(days=35)).strftime("%Y-%m-%d")

    m_days = re.search(r"(\d+)\s+days?\s+ago", low)
    if m_days:
        days_ago = int(m_days.group(1))
        return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    # Standard YYYY-MM-DD prefix
    m_iso = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m_iso:
        return m_iso.group(1)

    return s


def normalize_raw_jobs(raw_jobs: List[RawJob]) -> List[NormalizedJob]:
    """
    Converts a list of RawJob objects from different collectors into deduplicated
    NormalizedJob records with standardized timestamps and IDs.
    """
    now_iso = datetime.now().isoformat(timespec="seconds")
    unique_map: Dict[str, NormalizedJob] = {}

    for r in raw_jobs:
        job_id = compute_canonical_job_id(r)
        if job_id in unique_map:
            continue

        clean_title = r.title.strip()
        clean_company = r.company.strip() or "Hiring Company"
        # Strip trailing " - Company" if duplicated in title
        suffix = f" - {clean_company}"
        if clean_title.lower().endswith(suffix.lower()):
            clean_title = clean_title[: -len(suffix)].strip()

        posted = standardize_posted_date(r.posted_at)

        unique_map[job_id] = NormalizedJob(
            job_id=job_id,
            platform=r.platform.strip().lower(),
            company=clean_company,
            title=clean_title,
            location=(r.location or "").strip(),
            job_url=r.job_url.strip(),
            description=(r.description or "").strip(),
            posted_at=posted,
            first_seen_at=now_iso,
            last_seen_at=now_iso,
        )

    return list(unique_map.values())
