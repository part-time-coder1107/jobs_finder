from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import html
import re
from typing import List, Dict, Any
import requests
from src.collectors.base import BaseCollector
from src.models import RawJob


class LeverCollector(BaseCollector):
    """
    Collects published job postings from the official Lever Postings API:
    https://api.lever.co/v0/postings/{company_slug}?mode=json
    Uses concurrent requests and resolves multi-city (`allLocations`) and `workplaceType` fields.
    """

    platform_name = "lever"

    def collect(
        self,
        roles: List[str],
        locations: List[str],
        config: Dict[str, Any],
    ) -> List[RawJob]:
        boards = (config.get("company_boards") or {}).get("lever") or []
        collected: List[RawJob] = []

        def _fetch_board(board: Dict[str, Any]) -> List[RawJob]:
            slug = board.get("slug", "").strip()
            company_name = board.get("name", slug.title())
            if not slug:
                return []

            url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
            board_jobs: List[RawJob] = []
            try:
                resp = requests.get(url, timeout=6)
                if resp.status_code != 200:
                    return []
                postings = resp.json()
                if not isinstance(postings, list):
                    return []

                for p in postings:
                    title = (p.get("text") or "").strip()
                    categories = p.get("categories") or {}
                    primary_loc = (categories.get("location") or "").strip()
                    all_locs = [str(x).strip() for x in (categories.get("allLocations") or []) if str(x).strip()]
                    workplace_type = (p.get("workplaceType") or "").strip().lower()

                    loc_parts = []
                    if primary_loc:
                        loc_parts.append(primary_loc)
                    for al in all_locs:
                        if al.lower() not in " | ".join(loc_parts).lower():
                            loc_parts.append(al)
                    if workplace_type == "remote" and "remote" not in " | ".join(loc_parts).lower():
                        loc_parts.append("Remote")
                    loc = ", ".join(loc_parts)

                    team = categories.get("team") or ""
                    commitment = categories.get("commitment") or ""
                    hosted_url = (p.get("hostedUrl") or "").strip()
                    desc_plain = (p.get("descriptionPlain") or "").strip()
                    additional_plain = (p.get("additionalPlain") or "").strip()
                    raw_lists = " ".join(
                        [
                            f"{lst.get('text', '')}: {lst.get('content') or ''}"
                            for lst in (p.get("lists") or [])
                            if isinstance(lst, dict)
                        ]
                    )
                    clean_lists = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(raw_lists))).strip()
                    full_desc = f"Team: {team}. Type: {commitment}. {desc_plain} {clean_lists} {additional_plain}".strip()[:12000]

                    created_ms = p.get("createdAt")
                    posted_str = "Unknown"
                    if created_ms:
                        try:
                            posted_str = datetime.fromtimestamp(created_ms / 1000.0).strftime("%Y-%m-%d")
                        except Exception:
                            posted_str = "Unknown"

                    ext_id = str(p.get("id") or "")
                    if title and hosted_url:
                        board_jobs.append(
                            RawJob(
                                platform="lever",
                                company=company_name,
                                title=title,
                                location=loc,
                                job_url=hosted_url,
                                description=full_desc,
                                posted_at=posted_str,
                                external_id=f"lv_{slug}_{ext_id}" if ext_id else "",
                            )
                        )
            except Exception:
                return []
            return board_jobs

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_fetch_board, b) for b in boards]
            for fut in as_completed(futures):
                try:
                    collected.extend(fut.result())
                except Exception:
                    continue

        return collected
