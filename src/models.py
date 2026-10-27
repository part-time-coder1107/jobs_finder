from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


@dataclass
class RawJob:
    platform: str
    company: str
    title: str
    location: str
    job_url: str
    description: str = ""
    posted_at: str = "Unknown"
    external_id: str = ""


@dataclass
class NormalizedJob:
    job_id: str
    platform: str
    company: str
    title: str
    location: str
    job_url: str
    description: str
    posted_at: str
    first_seen_at: str
    last_seen_at: str
    match_score: float = 0.0
    role_category: str = "General"
    experience_level: str = "Entry-level"
    eligibility: str = "Likely eligible"
    matching_skills: List[str] = field(default_factory=list)
    why_it_matches: str = ""
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScanSummary:
    user_name: str
    recipient_email: str
    scan_time: str
    total_collected: int
    new_jobs_discovered: int
    strong_matches_count: int
    verification_needed_count: int
    previously_reported_excluded: int
    ranked_new_jobs: List[NormalizedJob] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_name": self.user_name,
            "recipient_email": self.recipient_email,
            "scan_time": self.scan_time,
            "total_collected": self.total_collected,
            "new_jobs_discovered": self.new_jobs_discovered,
            "strong_matches_count": self.strong_matches_count,
            "verification_needed_count": self.verification_needed_count,
            "previously_reported_excluded": self.previously_reported_excluded,
            "ranked_new_jobs": [j.to_dict() for j in self.ranked_new_jobs],
        }
