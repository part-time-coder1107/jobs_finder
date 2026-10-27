---
name: personal-job-agent
description: Personal AI job-search engine that collects jobs from Greenhouse, Lever, and Workday, deduplicates listings in SQLite, ranks opportunities (0-100) by technical profile, and sends a daily Gmail digest.
---

# Personal AI Job-Search Agent Skill (`personal-job-agent`)

Use this skill when the user wants to search for newly posted job opportunities across **Greenhouse**, **Lever**, and **Workday**, update their job preferences (`config/job_preferences.yaml`), or trigger their consolidated Gmail job report.

## Commands Available to the Agent

1. **Run a live scan and return structured JSON**:
   ```bash
   python -m src.main --run-once --json
   ```
2. **Search a specific role and locations on-demand**:
   ```bash
   python -m src.main --run-once --role "Machine Learning Engineer" --locations "Bengaluru, Remote" --json
   ```
3. **Start the 10:00 AM & 10:00 PM IST automated scheduler**:
   ```bash
   python -m src.main --schedule
   ```

## Configuration File
User preferences (name, email, active roles, locations including `Remote`, candidate skills, and excluded seniority keywords) are stored in `config/job_preferences.yaml`.
