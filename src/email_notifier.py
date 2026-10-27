from datetime import datetime
import os
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any
from src.models import ScanSummary
from database import get_setting, log_email


def _format_recency_label(posted_at: str) -> str:
    s = (posted_at or "").strip()
    if not s or s.lower() in ("unknown", "recent"):
        return "Recently, subject to verification."
    try:
        pdate = datetime.strptime(s[:10], "%Y-%m-%d").date()
        delta = (datetime.now().date() - pdate).days
        if delta == 0:
            return f"{s[:10]} (Posted Today)"
        if delta == 1:
            return f"{s[:10]} (Posted Yesterday)"
        if delta > 1:
            return f"{s[:10]} ({delta} days ago)"
    except Exception:
        pass
    return f"{s}, subject to verification."


def format_plain_text_digest(summary: ScanSummary) -> str:
    """
    Formats the plain-text job report in the exact consolidated format:
    Hi <Name>,
    Here is your job-search report for the latest scan.
    New opportunities found: N
    ...
    Summary
    New jobs discovered: ...
    Strong matches: ...
    Jobs requiring eligibility verification: ...
    Previously reported jobs excluded: ...
    """
    lines = [
        f"Hi {summary.user_name},",
        "",
        "Here is your job-search report for the latest scan.",
        f"New opportunities found: {summary.new_jobs_discovered}",
        "",
    ]

    if not summary.ranked_new_jobs:
        lines.extend(
            [
                "No new jobs posted since last activity.",
                "",
            ]
        )

    for idx, job in enumerate(summary.ranked_new_jobs, start=1):
        posted_label = _format_recency_label(job.posted_at)
        lines.extend(
            [
                f"{idx}. {job.title}",
                f"Company: {job.company}",
                f"Location: {job.location}",
                f"Match: {int(job.match_score)}/100",
                f"Why it matches: {job.why_it_matches}",
                f"Posted: {posted_label}",
                f"Apply: {job.job_url}",
                "",
            ]
        )

    lines.extend(
        [
            "Summary",
            f"New jobs discovered: {summary.new_jobs_discovered}",
            f"Strong matches: {summary.strong_matches_count}",
            f"Previously reported jobs excluded: {summary.previously_reported_excluded}",
            "",
            "Good luck with your applications!",
        ]
    )
    return "\n".join(lines)


def format_html_digest(summary: ScanSummary) -> str:
    cards_html = ""
    if not summary.ranked_new_jobs:
        cards_html = """
        <div style="border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; margin-bottom: 14px; background: #f8fafc; color: #334155; font-size: 14px;">
            <strong>No new jobs posted since last activity.</strong> All matching openings currently live on Workday, Greenhouse, and Lever were already sent in your previous report.
        </div>
        """
    for idx, job in enumerate(summary.ranked_new_jobs, start=1):
        posted_label = _format_recency_label(job.posted_at)
        score_int = int(job.match_score)
        score_bg = "#dcfce7" if score_int >= 80 else "#e0f2fe"
        score_fg = "#15803d" if score_int >= 80 else "#0369a1"

        cards_html += f"""
        <div style="border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; margin-bottom: 14px; background: #ffffff;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-size: 16px; font-weight: 700; color: #0f172a;">
                    {idx}. {job.title}
                </span>
                <span style="background: {score_bg}; color: {score_fg}; font-weight: 700; font-size: 12px; padding: 3px 10px; border-radius: 999px;">
                    Match: {score_int}/100
                </span>
            </div>
            <div style="font-size: 13.5px; color: #334155; line-height: 1.65;">
                <strong>Company:</strong> {job.company}<br/>
                <strong>Location:</strong> {job.location}<br/>
                <strong>Why it matches:</strong> {job.why_it_matches}<br/>
                <strong>Posted:</strong> {posted_label}<br/>
                <strong>Apply:</strong> <a href="{job.job_url}" target="_blank" style="color: #2563eb; font-weight: 600;">Application link &rarr;</a>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; padding: 24px; color: #0f172a;">
        <div style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px;">
            <p style="margin-top: 0; font-size: 15px;">Hi <strong>{summary.user_name}</strong>,</p>
            <p style="font-size: 14px; color: #334155;">
                Here is your job-search report for the latest scan.<br/>
                <strong>New opportunities found: {summary.new_jobs_discovered}</strong>
            </p>
            {cards_html}
            <div style="background: #f1f5f9; border-radius: 8px; padding: 14px 16px; margin-top: 18px; font-size: 13.5px; line-height: 1.7;">
                <strong>Summary</strong><br/>
                New jobs discovered: {summary.new_jobs_discovered}<br/>
                Strong matches: {summary.strong_matches_count}<br/>
                Previously reported jobs excluded: {summary.previously_reported_excluded}
            </div>
            <p style="font-size: 14px; color: #475569; margin-bottom: 0; margin-top: 16px;">
                Good luck with your applications!
            </p>
        </div>
    </body>
    </html>
    """


def send_consolidated_digest(summary: ScanSummary) -> Dict[str, Any]:
    """
    Sends the consolidated job report via Gmail SMTP and logs the digest to SQLite.
    If 0 new jobs were posted since the last activity, sends a status email confirming
    that no new jobs were posted since the last activity.
    """
    if summary.new_jobs_discovered == 0:
        subject = "Job-Search Report: No New Jobs Posted Since Last Activity"
    else:
        subject = f"Job-Search Report: {summary.new_jobs_discovered} New Opportunities Found ({summary.strong_matches_count} Strong Matches)"
    plain_text = format_plain_text_digest(summary)
    html_body = format_html_digest(summary)

    smtp_email = (get_setting("SMTP_EMAIL", "") or os.environ.get("SMTP_EMAIL", "")).strip()
    raw_password = (get_setting("SMTP_APP_PASSWORD", "") or os.environ.get("SMTP_APP_PASSWORD", "")).strip()
    # Strip all spaces (including non-breaking spaces \xa0 copied from Google's App Password popup)
    smtp_password = re.sub(r"\s+", "", raw_password)
    smtp_host = (get_setting("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com").strip()
    smtp_port = int(get_setting("SMTP_PORT", "587") or 587)

    if smtp_email and smtp_password and summary.recipient_email and "@" in summary.recipient_email:
        last_err = ""
        for attempt in range(3):
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = f"Personal AI Job Agent <{smtp_email}>"
                msg["To"] = summary.recipient_email
                msg.attach(MIMEText(plain_text, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                    server.ehlo()
                    server.starttls()
                    server.login(smtp_email, smtp_password)
                    server.sendmail(smtp_email, [summary.recipient_email], msg.as_string())

                print(f"\n[Email] ✓ Report successfully delivered to {summary.recipient_email} via Gmail SMTP.")
                return log_email(
                    subscription_id=None,
                    recipient_email=summary.recipient_email,
                    subject=subject,
                    html_body=html_body,
                    jobs_count=summary.new_jobs_discovered,
                    status="sent_smtp",
                    delivery_mode="gmail_smtp",
                )
            except Exception as e:
                last_err = str(e)
                if attempt < 2:
                    time.sleep(5)

        print(f"\n[Email] ✗ Gmail SMTP delivery failed for {summary.recipient_email}: {last_err}")
        return log_email(
            subscription_id=None,
            recipient_email=summary.recipient_email,
            subject=subject,
            html_body=html_body,
            jobs_count=summary.new_jobs_discovered,
            status="failed",
            delivery_mode="gmail_smtp",
            error_msg=last_err,
        )

    print(f"\n[Email] ✗ Skipped email delivery: SMTP_EMAIL or SMTP_APP_PASSWORD is missing.")

    return log_email(
        subscription_id=None,
        recipient_email=summary.recipient_email,
        subject=subject,
        html_body=html_body,
        jobs_count=summary.new_jobs_discovered,
        status="preview_only",
        delivery_mode="in_app_preview",
        error_msg="Saved report in local SQLite log (Set SMTP_EMAIL & SMTP_APP_PASSWORD in .env for Gmail delivery).",
    )
