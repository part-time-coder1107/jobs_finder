---
name: personal-job-watcher
description: Checks Greenhouse, Lever, and Workday at 12:00 Noon and 12:00 Midnight (signing in with the user's email where required), finds new jobs for the target role and locations, deduplicates against seen_jobs.json, and sends a Gmail summary.
---

# Personal Job Watcher (12:00 Noon & 12:00 Midnight Gmail Summary)

You are an automated job-search agent running natively inside **OpenClaw**.

---

## Step 1: Load User Profile & Seen Jobs

1. Read `job_profile.md` (in the same skill folder) to get:
   - `Name`
   - `Gmail Address` and `Gmail 16-Char App Password`
   - `Portal Sign-In Email`
   - `Target Job Role`
   - `Target Locations` (including `Remote`)
2. Read `seen_jobs.json` to get `reported_job_urls` so you never email the same job twice.

---

## Step 2: Check Greenhouse, Lever & Workday

Check all three platforms for the **Target Job Role** and **Target Locations**:

1. **Greenhouse (`greenhouse.io`)**:
   - Use `web_fetch` on company boards:
     - `https://boards-api.greenhouse.io/v1/boards/stripe/jobs`
     - `https://boards-api.greenhouse.io/v1/boards/databricks/jobs`
     - `https://boards-api.greenhouse.io/v1/boards/rubrik/jobs`
     - `https://boards-api.greenhouse.io/v1/boards/okta/jobs`
     - `https://boards-api.greenhouse.io/v1/boards/mongodb/jobs`
     - `https://boards-api.greenhouse.io/v1/boards/coupang/jobs`
     - `https://boards-api.greenhouse.io/v1/boards/toast/jobs`
2. **Lever (`jobs.lever.co`)**:
   - Use `web_fetch` on company boards:
     - `https://api.lever.co/v0/postings/meesho?mode=json`
     - `https://api.lever.co/v0/postings/zeta?mode=json`
     - `https://api.lever.co/v0/postings/cred?mode=json`
     - `https://api.lever.co/v0/postings/veeva?mode=json`
3. **Workday (`myworkdayjobs.com`) & Browser Sign-In**:
   - Use `web_search` or the `browser` tool to check Workday career portals (`myworkdayjobs.com`) for the target role and locations.
   - If any portal prompts for candidate email/sign-in to view openings, use the `browser` tool with the user's `Portal Sign-In Email`.

---

## Step 3: Filter & Deduplicate (Last 14 Days Only + Never Repeat Sent Jobs)

1. **Strict 14-Day Recency Rule**: Keep **only** jobs posted within the **last 14 days** (`0 <= days_since_posted <= 14`). Discard any job older than 14 days (including Workday's `Posted 30+ Days Ago` or old evergreen postings).
2. **All Companies (Prioritize Workday & Greenhouse)**: Search across all companies on Workday (`myworkdayjobs.com`), Greenhouse (`greenhouse.io`), and Lever (`jobs.lever.co`), prioritizing Workday and Greenhouse openings and returning up to 50+ matching jobs.
3. **Location & Role Match**: Keep only jobs matching the **Target Job Role** and **Target Locations** (match `Bengaluru` with `Bangalore`, `Gurugram` with `Gurgaon`, and include `Remote` roles open to India while excluding US/Canada/UK-only Remote).
4. **Strict Deduplication Across Emails**: Remove any job that has already been sent in a previous email (`notifications` table in `jobs_watcher.db` and `seen_jobs.json`). Once a job is emailed, record it immediately so it **never** appears in the next email.

---

## Step 4: Send the Summary Email to Gmail

Format the email body as:

```text
Hi [Name],

Here is your 12-hour job-search summary across Greenhouse, Lever, and Workday:
Role: [Target Job Role]
Locations: [Target Locations]
New opportunities found: [N]

1. [Job Title] — [Company]
   Platform: [Greenhouse / Lever / Workday]
   Location: [Location]
   Apply Link: [Direct URL]

...
```

Send this summary to the user's Gmail using OpenClaw's shell/exec tool with built-in Windows PowerShell SMTP (using the Gmail Address and 16-char App Password from `job_profile.md`):

```powershell
$EmailFrom = "<Gmail Address from job_profile.md>"
$EmailTo   = "<Gmail Address from job_profile.md>"
$AppPass   = "<Gmail 16-Char App Password from job_profile.md>"
$Subject   = "New Job Summary: <N> New <Role> Openings on Greenhouse, Lever & Workday"
$Body      = @"
<Formatted Summary Body>
"@

$Smtp = New-Object Net.Mail.SmtpClient("smtp.gmail.com", 587)
$Smtp.EnableSsl = $true
$Smtp.Credentials = New-Object System.Net.NetworkCredential($EmailFrom, $AppPass)
$Smtp.Send($EmailFrom, $EmailTo, $Subject, $Body)
```
