# ⚡ Personal AI Job-Search Agent (Terminal Edition)

An automated, zero-cost personal job-search agent that monitors **Greenhouse** (`greenhouse.io`), **Workday** (`myworkdayjobs.com`), and **Lever** (`jobs.lever.co`) career portals for newly posted fresher / 0–3 years roles (posted within the last 14 days) across all your chosen locations, sorted strictly in order of recency (`Posted Today` $\rightarrow$ `Yesterday` $\rightarrow$ `...` $\rightarrow$ `14 days ago`), and delivers a daily consolidated Gmail report.

---

## 🚀 Quick Start (Clone & Setup on Any Laptop)

### 1. Clone the Repository
Open your terminal (PowerShell or Command Prompt) and run:
```bash
git clone https://github.com/part-time-coder1107/jobs_finder.git
cd jobs_finder
```

### 2. Install Dependencies
Make sure you have **Python 3.10+** installed, then install the required packages:
```bash
pip install -r requirements.txt
```

### 3. Run the Interactive Terminal Setup Wizard
```bash
python setup_agent.py
```
*(or `python -m src.main --setup`)*

Inside the terminal wizard, you will configure:
1. **Full Name**: Your name for the daily email greeting.
2. **Recipient Gmail Address**: The email address where your daily job report will be sent.
3. **Gmail 16-Character App Password**:
   - Create a 16-character Google App Password at **[https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)** (requires 2-Step Verification enabled on your Google Account) and paste it here.
4. **Target Job Role (Single Role)**:
   - Use the `↑` / `↓` arrow keys and press `ENTER` to tick `[✓]` one role (e.g., `Software Engineer`, `Machine Learning Engineer`, `AI Engineer`, `Data Analyst`, `Product Analyst`, `Data Scientist`, `Backend Engineer`, `Frontend Engineer`, or choose `Type a Custom Job Role...` to enter any role).
5. **Target Locations (Multi-Select)**:
   - Use `↑` / `↓` arrow keys and press `SPACEBAR` to tick `[✓]` multiple locations (including `Remote`, `Bengaluru`, `Hyderabad`, `Pune`, `Gurugram`, `Mumbai`, `Chennai`, `Delhi NCR`), then press `ENTER`.
6. **Job Portals to Search (Multi-Select)**:
   - Use `SPACEBAR` to tick `[✓]` `Greenhouse`, `Workday`, and `Lever`, then press `ENTER`.

At the end of the setup, type `y` when asked:
```text
Would you like to run a live scan & send a test email right now? (y/n) [n]: y
```
to immediately run your first scan and receive your email report!

---

## ⏰ Automatic 11:00 AM Daily Check + Closed-Laptop Wake-Up

When you finish `python setup_agent.py`, the agent automatically configures:
- **11:00 AM Daily Timer**: Scheduled via Windows Task Scheduler (`JobAgent_Daily`) and the background Windows Startup watcher (`JobAgent_12PM_Watcher.vbs`).
- **Wake-Up & Post-11:00 AM Catch-Up**:
  - If your laptop is open at **11:00 AM**, the scan runs at 11:00 AM and emails your report.
  - If your laptop was **closed (asleep) or turned off** at 11:00 AM, as soon as you open or turn on your laptop later that day and Wi-Fi connects, the agent automatically detects that today's 11:00 AM check was missed, runs the scan once, and emails all new jobs posted since your last check.

---

## 🛠️ Useful Terminal Commands

- **Re-run the interactive setup / change preferences anytime**:
  ```bash
  python setup_agent.py
  ```
- **Run an immediate scan & send email right now**:
  ```bash
  python -m src.main --run-once
  ```
- **Run a scan for a specific role or locations from CLI**:
  ```bash
  python -m src.main --run-once --role "Data Analyst" --locations "Remote, Bengaluru, Hyderabad, Pune"
  ```

---

## ✨ Key Features

- **100% Free Public ATS Feeds**: Queries Greenhouse, Workday, and Lever directly — no paid API keys, no LLM tokens, and no credit limits.
- **Last 14 Days Only & Sorted by Recency**: Filters strictly for jobs posted within the last 14 days and sorts them from `Posted Today` down to `14 days ago`.
- **Zero Duplicate Emails**: Every emailed job is recorded in a dedicated per-user SQLite database (`data/user_dbs/<your_email>.db`) using 3-key deduplication (`job_id`, `canonical_url`, and `company|title`) so the same job is never emailed twice.
