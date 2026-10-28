from datetime import datetime
import re
from typing import List, Dict, Any
from src.models import NormalizedJob
from src.normalizer import expand_location_aliases

ROLE_SYNONYM_GROUPS = {
    "machine learning": [
        "machine learning",
        "ml engineer",
        "ai engineer",
        "applied scientist",
        "deep learning",
        "computer vision",
        "nlp",
        "genai",
        "llm",
        "ai/ml",
    ],
    "ai engineer": [
        "ai engineer",
        "artificial intelligence",
        "genai",
        "generative ai",
        "llm",
        "rag",
        "machine learning",
        "applied ai",
        "ai/ml",
        "agentic",
    ],
    "data scientist": [
        "data scientist",
        "decision scientist",
        "machine learning",
        "applied scientist",
        "research scientist",
        "quantitative analyst",
    ],
    "product analyst": [
        "product analyst",
        "business analyst",
        "data analyst",
        "product analytics",
        "decision scientist",
        "growth analyst",
        "insights analyst",
    ],
    "business analyst": [
        "business analyst",
        "product analyst",
        "data analyst",
        "business analytics",
        "operations analyst",
        "strategy analyst",
    ],
    "data analyst": [
        "data analyst",
        "business analyst",
        "product analyst",
        "analytics",
        "bi analyst",
        "business intelligence",
        "reporting analyst",
        "risk analyst",
        "operations analyst",
        "insights analyst",
    ],
    "data engineer": [
        "data engineer",
        "analytics engineer",
        "big data engineer",
        "etl developer",
        "data platform engineer",
        "data infrastructure",
    ],
    "backend engineer": [
        "backend engineer",
        "back-end engineer",
        "backend developer",
        "back end engineer",
        "software engineer - backend",
        "software engineer, backend",
        "server engineer",
        "api engineer",
        "distributed systems engineer",
    ],
    "frontend engineer": [
        "frontend engineer",
        "front-end engineer",
        "frontend developer",
        "front end engineer",
        "ui engineer",
        "web developer",
        "react developer",
        "software engineer - frontend",
        "software engineer, frontend",
    ],
    "full stack": [
        "full stack",
        "fullstack",
        "full-stack",
        "software engineer - full stack",
        "software engineer, full stack",
    ],
    "devops": [
        "devops",
        "site reliability",
        "sre",
        "platform engineer",
        "cloud engineer",
        "infrastructure engineer",
        "release engineer",
    ],
    "cloud engineer": [
        "cloud engineer",
        "devops",
        "site reliability",
        "sre",
        "platform engineer",
        "aws engineer",
        "azure engineer",
        "gcp engineer",
        "cloud infrastructure",
    ],
    "qa engineer": [
        "qa engineer",
        "quality assurance",
        "test engineer",
        "sdet",
        "software development engineer in test",
        "automation engineer",
        "quality engineer",
    ],
    "security engineer": [
        "security engineer",
        "cybersecurity",
        "application security",
        "appsec",
        "infosec",
        "information security",
        "security analyst",
        "cloud security",
    ],
    "android": [
        "android",
        "mobile engineer",
        "mobile developer",
    ],
    "ios": [
        "ios",
        "mobile engineer",
        "mobile developer",
    ],
    "product manager": [
        "product manager",
        "associate product manager",
        "apm",
        "product owner",
        "technical product manager",
    ],
    "software engineer": [
        "software engineer",
        "software developer",
        "software development engineer",
        "system software engineer",
        "systems software engineer",
        "sde",
        "backend engineer",
        "frontend engineer",
        "full stack",
        "fullstack",
        "applications engineer",
        "application developer",
        "associate software engineer",
        "graduate engineer",
        "member of technical staff",
    ],
}

ROLE_DEFAULT_SKILLS = {
    "Machine Learning": ["Python", "PyTorch", "machine learning", "computer vision"],
    "AI / GenAI": ["LLM applications", "RAG", "Python", "agent development"],
    "Product & Analytics": ["SQL", "product metrics", "analytical problem-solving", "experimentation"],
    "Data Science": ["Python", "SQL", "statistical modeling", "machine learning"],
    "Software Engineering": ["Python", "distributed systems", "APIs", "software engineering"],
}

NON_INDIA_REMOTE_MARKERS = [
    "us-remote",
    "us - remote",
    "remote us",
    "remote - us",
    "remote - usa",
    "remote, us",
    "remote in us",
    "united states",
    "canada-remote",
    "canada - remote",
    "remote canada",
    "remote - canada",
    "remote, canada",
    "remote in canada",
    "canada",
    "uk-remote",
    "remote uk",
    "remote - uk",
    "remote, united kingdom",
    "united kingdom",
    "ireland",
    "spain",
    "emea",
    "latam",
    "brazil",
    "mexico",
    "poland",
    "romania",
    "germany",
    "japan",
    "australia",
    "singapore",
    "korea",
    "taiwan",
]


def _is_posted_within_days(posted_at: str, max_days: int = 14) -> bool:
    """
    Strictly verifies that the job was posted within the last `max_days` (default 14 days).
    Jobs older than 14 days or with unknown dates are excluded.
    """
    s = (posted_at or "").strip()
    if not s or s.lower() == "unknown":
        return False
    try:
        posted_date = datetime.strptime(s[:10], "%Y-%m-%d").date()
        today = datetime.now().date()
        delta_days = (today - posted_date).days
        return 0 <= delta_days <= max_days
    except Exception:
        return False


def _infer_role_category(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    if re.search(r"\b(llm|rag|genai|generative ai|agentic)\b", text):
        return "AI / GenAI"
    if re.search(r"\b(machine learning|ml engineer|computer vision|deep learning|pytorch)\b", text):
        return "Machine Learning"
    if re.search(r"\b(product analyst|business analyst|data analyst|analytics|bi analyst)\b", text):
        return "Product & Analytics"
    if re.search(r"\b(data scientist|decision scientist)\b", text):
        return "Data Science"
    return "Software Engineering"


def _matches_target_roles(title: str, description: str, target_roles: List[str]) -> bool:
    jt = title.lower()

    # Reject non-tech / non-analytics functions immediately
    if re.search(r"\b(legal|counsel|recruiter|recruiting|sales|account executive|mandarin|payroll|tax|audit)\b", jt):
        return False

    for role in target_roles:
        r_low = role.strip().lower()
        if not r_low:
            continue
        if r_low in jt:
            return True
        for key, syns in ROLE_SYNONYM_GROUPS.items():
            if key in r_low or r_low in key:
                if any(s in jt for s in syns):
                    return True
        tokens = [w for w in r_low.split() if len(w) > 2]
        if tokens and all(t in jt for t in tokens):
            return True

    return False


def _is_location_compatible(job_loc: str, allowed_loc_terms: List[str]) -> bool:
    if not allowed_loc_terms:
        return True
    loc_low = job_loc.lower()

    city_terms = [t for t in allowed_loc_terms if "remote" not in t and t != "anywhere" and t != "work from home"]
    if any(ct in loc_low for ct in city_terms):
        return True

    wants_remote = any("remote" in t for t in allowed_loc_terms)
    if wants_remote and ("remote" in loc_low or "work from home" in loc_low):
        if any(foreign in loc_low for foreign in NON_INDIA_REMOTE_MARKERS) and "india" not in loc_low:
            return False
        return True

    return False


def _is_excluded_by_seniority(title: str, exclude_keywords: List[str], target_roles: List[str]) -> bool:
    tl = title.lower()
    if any(ex in tl for ex in exclude_keywords):
        return True
    if re.search(r"\b(sr\.?|senior|staff|principal|director|vp|head of|distinguished)\b", tl):
        if not any("senior" in r.lower() for r in target_roles):
            return True
    if re.search(r"\b(manager|management)\b", tl):
        if not any("manager" in r.lower() for r in target_roles):
            return True
    return False


_YEARS = r"(?:years?|yrs?)"
_MIN_YEARS_PATTERNS = [
    rf"\b(\d{{1,2}})\s*(?:-|–|to)\s*\d{{1,2}}\s*\+?\s*{_YEARS}",         # "0-2 years", "1-3 years", "4-6 years" (lower bound)
    rf"\b(\d{{1,2}})\s*\+\s*{_YEARS}",                                   # "1+ years", "2+ years", "4+ years"
    rf"\b(?:minimum|min\.?|at least|atleast)\s*(?:of\s*)?(\d{{1,2}})\s*\+?\s*{_YEARS}",  # "minimum 2 years", "at least 1 year"
    rf"\b(\d{{1,2}})\s*or more\s*{_YEARS}",                              # "2 or more years"
    rf"\b(\d{{1,2}})\s*{_YEARS}\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+|hands-on\s+)?experience\b",  # "2 years of experience"
]

_QUALIFICATION_HEADER_RE = re.compile(
    r"\b(minimum qualifications?|required qualifications?|basic qualifications?|qualifications?\s+required|qualifications?|requirements?|what you(?:'ll|\s+will)?\s+(?:need|bring)|who you are|eligibility|experience required)\b",
    re.IGNORECASE,
)


def _extract_qualification_section(description: str) -> str:
    """
    Extracts the 'Qualifications Required' / 'Requirements' section from the full
    job detail text so minimum years of experience can be read directly from the
    qualifications section.
    """
    desc = description or ""
    matches = list(_QUALIFICATION_HEADER_RE.finditer(desc))
    if not matches:
        return desc
    # Combine slices around each qualification/requirement heading (up to 3500 chars each)
    slices = [desc[m.start() : m.start() + 3500] for m in matches]
    return " ".join(slices)


def _is_zero_to_two_years_qualification(title: str, description: str) -> bool:
    """
    Reads the Qualification Required section of the job details (and title/full details)
    to determine the minimum years of experience required.
    Returns True if the minimum experience is in the range of 0-2 years (0, 1, or 2 years,
    or explicit fresher / entry-level / new graduate role) so those jobs are placed ON TOP,
    and False for all other jobs so they are placed BELOW them.
    """
    qual_section = _extract_qualification_section(description).lower()
    full_text = f"{title} {description}".lower()

    # Check the extracted Qualification section first, then full job details
    for section_text in (qual_section, full_text):
        found_min_years: List[int] = []
        for pattern in _MIN_YEARS_PATTERNS:
            for m in re.finditer(pattern, section_text):
                try:
                    yr = int(m.group(1))
                    if 0 <= yr <= 25:
                        found_min_years.append(yr)
                except (ValueError, IndexError):
                    continue

        if found_min_years:
            min_required = min(found_min_years)
            return 0 <= min_required <= 2

    # Also treat explicit fresher / new-grad / entry-level / I / Associate / Graduate roles as 0-2 years
    if re.search(
        r"\b(fresher|new grad|recent graduate|university graduate|entry[- ]level|graduate engineer|associate|intern|0\s*years?)\b",
        full_text,
    ):
        return True

    return False


def filter_and_rank_jobs(
    jobs: List[NormalizedJob],
    roles: List[str],
    locations: List[str],
    config: Dict[str, Any],
) -> List[NormalizedJob]:
    """
    Executes the matching and ranking pipeline:
    1. Filters by Last 14 Days + Location + Role (with no restriction on the number of jobs).
    2. Reads the Qualification section of every job detail to check if minimum experience is 0-2 years.
    3. Places 0-2 years experience jobs ON TOP (sorted by recency) and all other jobs BELOW them (sorted by recency).
    """
    profile_cfg = config.get("candidate_profile") or {}

    core_skills: List[str] = profile_cfg.get("core_skills") or [
        "Python", "PyTorch", "Machine Learning", "Computer Vision", "RAG", "LangChain", "SQL"
    ]
    exclude_keywords: List[str] = [
        k.lower() for k in (profile_cfg.get("exclude_title_keywords") or ["Senior", "Staff", "Principal", "Director", "VP"])
    ]

    user_wants_senior = any("senior" in r.lower() for r in roles)
    if user_wants_senior and "senior" in exclude_keywords:
        exclude_keywords.remove("senior")

    allowed_loc_terms = expand_location_aliases(locations)
    ranked_jobs: List[NormalizedJob] = []

    for job in jobs:
        # --- STAGE 1: RULE-BASED FILTERING (Last 14 Days + Location + Seniority + Role) ---
        if not _is_posted_within_days(job.posted_at, max_days=14):
            continue

        if not _is_location_compatible(job.location, allowed_loc_terms):
            continue

        if _is_excluded_by_seniority(job.title, exclude_keywords, roles):
            continue

        if not _matches_target_roles(job.title, job.description, roles):
            continue

        # --- STAGE 2: PROFILE & SKILL MATCH SCORING (0-100) ---
        category = _infer_role_category(job.title, job.description)

        full_text = f"{job.title} {job.description}".lower()
        matched_skills: List[str] = []
        for sk in core_skills:
            pattern = rf"\b{re.escape(sk.lower())}\b"
            if re.search(pattern, full_text):
                matched_skills.append(sk)

        base_score = 72
        if any(r.lower() in job.title.lower() for r in roles):
            base_score += 8
        if job.platform in ("workday", "greenhouse"):
            base_score += 4
        skill_bonus = min(16, len(matched_skills) * 4)
        raw_score = base_score + skill_bonus
        final_score = max(55, min(98, raw_score))

        display_skills = matched_skills[:4] if matched_skills else ROLE_DEFAULT_SKILLS.get(category, ["Python", "problem-solving"])
        if len(display_skills) > 1:
            why_str = ", ".join(display_skills[:-1]) + f", and {display_skills[-1]}."
        else:
            why_str = f"{display_skills[0]}."

        job.role_category = category
        job.match_score = float(final_score)
        job.matching_skills = display_skills
        job.why_it_matches = why_str

        ranked_jobs.append(job)

    # Sort Order:
    # 1. Jobs with 0-2 years minimum experience in their Qualifications section ON TOP (1),
    #    followed by all other jobs BELOW them (0)
    # 2. Within each tier, most recent posting date FIRST (Posted Today -> Yesterday -> ... -> 14 days ago)
    # 3. Match score
    ranked_jobs.sort(
        key=lambda j: (
            1 if _is_zero_to_two_years_qualification(j.title, j.description) else 0,
            j.posted_at,
            j.match_score,
        ),
        reverse=True,
    )
    return ranked_jobs
