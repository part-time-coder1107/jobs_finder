from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import re
from typing import List, Dict, Any
import requests
from src.collectors.base import BaseCollector
from src.models import RawJob


class GreenhouseCollector(BaseCollector):
    """
    Collects published job postings from the official Greenhouse Job Board API:
    https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
    Uses concurrent requests across all configured Greenhouse boards.
    """

    platform_name = "greenhouse"

    def collect(
        self,
        roles: List[str],
        locations: List[str],
        config: Dict[str, Any],
    ) -> List[RawJob]:
        boards = (config.get("company_boards") or {}).get("greenhouse") or []
        collected: List[RawJob] = []

        def _fetch_board(board: Dict[str, Any]) -> List[RawJob]:
            slug = board.get("slug", "").strip()
            company_name = board.get("name", slug.title())
            if not slug:
                return []

            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
            board_jobs: List[RawJob] = []
            try:
                resp = requests.get(url, timeout=6)
                if resp.status_code != 200:
                    return []
                jobs_list = resp.json().get("jobs", [])
                for j in jobs_list:
                    title = j.get("title", "").strip()
                    loc_name = (j.get("location") or {}).get("name", "") or ""
                    offices = j.get("offices") or []
                    office_locs = []
                    for o in offices:
                        if not isinstance(o, dict):
                            continue
                        o_name = (o.get("name") or "").strip()
                        o_loc = (o.get("location") or "").strip()
                        combined_o = f"{o_name} {o_loc}".strip() if o_loc and o_loc.lower() not in o_name.lower() else (o_name or o_loc)
                        if combined_o:
                            office_locs.append(combined_o)
                    if office_locs:
                        extra_locs = ", ".join(ol for ol in office_locs if ol.lower() not in loc_name.lower())
                        if extra_locs:
                            loc_name = f"{loc_name} ({extra_locs})".strip() if loc_name else extra_locs
                    abs_url = j.get("absolute_url", "").strip()
                    updated_at = (j.get("updated_at") or j.get("first_published") or "")[:10] or "Unknown"
                    ext_id = str(j.get("id", ""))
                    raw_html = j.get("content", "") or ""

                    plain_desc = ""
                    if raw_html:
                        try:
                            unescaped = html.unescape(raw_html)
                            plain_desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescaped)).strip()[:12000]
                        except Exception:
                            plain_desc = raw_html[:1000]

                    if title and abs_url:
                        board_jobs.append(
                            RawJob(
                                platform="greenhouse",
                                company=company_name,
                                title=title,
                                location=loc_name,
                                job_url=abs_url,
                                description=plain_desc,
                                posted_at=updated_at,
                                external_id=f"gh_{slug}_{ext_id}" if ext_id else "",
                            )
                        )
            except Exception:
                return []
            return board_jobs

        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(_fetch_board, b) for b in boards]
            for fut in as_completed(futures):
                try:
                    collected.extend(fut.result())
                except Exception:
                    continue

        return collected
