from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from typing import List, Dict, Any
import requests
from src.collectors.base import BaseCollector
from src.models import RawJob


class WorkdayCollector(BaseCollector):
    """
    Collects job postings from Workday CXS JSON career portals across industries:
    POST https://{tenant}.{wd_instance}.myworkdayjobs.com/wday/cxs/{tenant}/{site_id}/jobs
    Uses concurrent requests and resolves Workday's '2 Locations' / '3 Locations'
    multi-city labels against the queried Indian cities.
    """

    platform_name = "workday"

    def collect(
        self,
        roles: List[str],
        locations: List[str],
        config: Dict[str, Any],
    ) -> List[RawJob]:
        boards = (config.get("company_boards") or {}).get("workday") or []
        collected: List[RawJob] = []

        search_terms = [r.strip() for r in roles if r.strip()]
        if not search_terms:
            return []

        # Build location queries from ALL user-specified locations so every selected
        # city (plus India for Remote/multi-city postings) is searched on Workday
        location_queries: List[str] = []
        seen_loc_q = set()
        for loc in locations:
            clean_loc = loc.strip()
            if not clean_loc:
                continue
            q = "India" if clean_loc.lower() == "remote" else clean_loc
            if q.lower() not in seen_loc_q:
                seen_loc_q.add(q.lower())
                location_queries.append(q)
        if "india" not in seen_loc_q:
            location_queries.append("India")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        def _fetch_board(board: Dict[str, Any]) -> List[RawJob]:
            tenant = board.get("tenant", "").strip()
            wd = board.get("wd_instance", "wd5").strip()
            site_id = board.get("site_id", "").strip()
            company_name = board.get("name", tenant.title())
            if not tenant or not site_id:
                return []

            api_url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site_id}/jobs"
            board_jobs: List[RawJob] = []
            seen_paths = set()

            for role_term in search_terms:
                for loc_q in location_queries:
                    try:
                        payload = {
                            "appliedFacets": {},
                            "limit": 20,
                            "offset": 0,
                            "searchText": f"{role_term} {loc_q}".strip(),
                        }
                        resp = requests.post(api_url, json=payload, headers=headers, timeout=6)
                        if resp.status_code != 200:
                            continue
                        postings = resp.json().get("jobPostings", [])
                        for p in postings:
                            title = (p.get("title") or "").strip()
                            loc_text = (p.get("locationsText") or loc_q).strip()
                            ext_path = (p.get("externalPath") or "").strip()
                            posted_on = (p.get("postedOn") or "Unknown").strip()
                            bullets = " ".join(p.get("bulletFields") or [])

                            if not title or not ext_path or ext_path in seen_paths:
                                continue
                            if "indiana" in ext_path.lower():
                                continue
                            seen_paths.add(ext_path)

                            # Workday's externalPath embeds the primary location slug, e.g. /job/India-Bengaluru/...
                            path_parts = [seg for seg in ext_path.split("/") if seg]
                            path_loc = path_parts[1].replace("---", ", ").replace("-", " ") if len(path_parts) >= 2 else ""

                            if re.match(r"^\d+\s+locations?$", loc_text.lower()) or loc_text.lower() == "india":
                                base_loc = f"{path_loc} ({loc_text})".strip() if path_loc else loc_text
                                if loc_q.lower() != "india" and loc_q.lower() not in base_loc.lower():
                                    resolved_loc = f"{base_loc}, {loc_q}"
                                else:
                                    resolved_loc = base_loc
                            else:
                                resolved_loc = loc_text

                            full_url = f"https://{tenant}.{wd}.myworkdayjobs.com/en-US/{site_id}{ext_path}"
                            board_jobs.append(
                                RawJob(
                                    platform="workday",
                                    company=company_name,
                                    title=title,
                                    location=resolved_loc,
                                    job_url=full_url,
                                    description=f"Workday requisition ({bullets}) at {company_name} in {resolved_loc}.",
                                    posted_at=posted_on,
                                    external_id=f"wd_{tenant}_{ext_path}",
                                )
                            )
                    except Exception:
                        continue
            return board_jobs

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_fetch_board, b) for b in boards]
            for fut in as_completed(futures):
                try:
                    collected.extend(fut.result())
                except Exception:
                    continue

        return collected
