# 🦞 OpenClaw Setup: 12:00 Noon & 12:00 Midnight Gmail Job Summary

This setup configures OpenClaw to check **Greenhouse**, **Lever**, and **Workday** (using OpenClaw's browser & web tools), find newly posted jobs for your role and locations, and **send a summary email to your Gmail at 12:00 Noon and 12:00 Midnight**.

---

## Step 1: Finish the `openclaw onboard` Wizard
1. On the **Channels** screen (`Skip for now`, `AgentMail`, `Discord`, etc.), press **Enter** on **`Skip for now`** *(note: `AgentMail` is a third-party chat service, not Gmail—we connect your actual Gmail below!)*.
2. Finish the remaining prompts until `openclaw onboard` completes.

---

## Step 2: Copy Your Job Watcher Skill into OpenClaw
Run this command in PowerShell to install the skill into your OpenClaw workspace:
```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.openclaw\workspace\skills\personal-job-watcher"
Copy-Item -Path "c:\Users\aryus\Downloads\jobs_finder\openclaw_agent\*" -Destination "$HOME\.openclaw\workspace\skills\personal-job-watcher\" -Recurse -Force
```

---

## Step 3: Schedule the 12:00 Noon & 12:00 Midnight Runs
Run these two commands in PowerShell to schedule OpenClaw at **12:00 PM (Noon)** and **12:00 AM (Midnight)** IST:

```powershell
# 1. 12:00 Noon IST Daily Check
openclaw cron add `
  --name "job-summary-12noon" `
  --cron "0 12 * * *" `
  --tz "Asia/Kolkata" `
  --session isolated `
  --message "Use the personal-job-watcher skill to check Greenhouse, Lever, and Workday for new jobs matching job_profile.md, update seen_jobs.json, and send the summary email to my Gmail."

# 2. 12:00 Midnight IST Daily Check
openclaw cron add `
  --name "job-summary-12midnight" `
  --cron "0 0 * * *" `
  --tz "Asia/Kolkata" `
  --session isolated `
  --message "Use the personal-job-watcher skill to check Greenhouse, Lever, and Workday for new jobs matching job_profile.md, update seen_jobs.json, and send the summary email to my Gmail."
```
