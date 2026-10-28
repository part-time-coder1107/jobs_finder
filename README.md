# Personal Job-Search Agent (Terminal Edition)

An automated, zero-cost personal job-search agent that scans **Greenhouse** (`greenhouse.io`), **Workday** (`myworkdayjobs.com`), and **Lever** (`jobs.lever.co`) career portals for newly posted roles (last 14 days), reads the **Qualifications Required** section of every job detail to place **0–2 years experience** roles on top (sorted by recency from `Posted Today` downwards), and sends a daily Gmail report at **11:00 AM**.

---

## Step 1: Turn On 2-Step Verification & Create Your 16-Character Gmail App Password

To allow the agent to email your daily job report to your Gmail inbox, Google requires a **16-Character App Password** (not your normal Gmail password).

### A. If Your Google 2-Step Verification (2FA) is Currently OFF:
1. Open **[https://myaccount.google.com/security](https://myaccount.google.com/security)** and sign in to your Google account.
2. Under **"How you sign in to Google"**, click **2-Step Verification**.
3. Click **Get started** (or **Turn on 2-Step Verification**) and follow the prompts to verify your phone number via SMS or Google Prompt.
4. Click **Turn On**.

### B. Generate Your 16-Character App Password:
1. Once 2-Step Verification is ON, open **[https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)**.
2. In the **App name** box, type `Job Agent` and click **Create**.
3. A yellow box will pop up showing a **16-letter code** (4 groups of 4 letters, e.g., `abcd efgh ijkl mnop`).
4. **Copy that 16-letter code** (keep it ready for Step 3 below).

---

## Step 2: Install Git (if not installed) & Clone the Repository

### A. If Git is NOT Installed on Your Laptop:
1. Open **PowerShell** or **Command Prompt** and run this command to install Git on Windows:
   ```bash
   winget install --id Git.Git -e --source winget
   ```
   *(Or download & install Git manually from [https://git-scm.com/download/win](https://git-scm.com/download/win))*
2. Once Git finishes installing, **close and reopen PowerShell / Command Prompt**, then verify Git is installed by running:
   ```bash
   git --version
   ```

### B. Clone the Repository & Run Setup:
Make sure **Python 3.10+** and **Git** are installed on your Windows laptop, then open **PowerShell** or **Command Prompt** and run these commands one by one:

```bash
cd ~
git clone https://github.com/part-time-coder1107/jobs_finder.git
cd jobs_finder
pip install -r requirements.txt
python setup_agent.py
```

---

## Step 3: Fill Your Details in the Terminal Setup (`python setup_agent.py`)

When `python setup_agent.py` starts, complete the prompts inside the terminal:

1. **Enter Full Name**: Type your name and press `ENTER`.
2. **Enter Recipient Gmail Address**: Type your Gmail address (e.g., `yourname@gmail.com`) and press `ENTER`.
3. **Enter Gmail 16-Character App Password**: Paste the **16-character App Password** you copied from Google in Step 1B and press `ENTER`.
4. **Select Target Job Role**:
   - Use the `↑` / `↓` arrow keys to move the `[✓]` tick-box to your preferred role (or select `Type a Custom Job Role...` to type any role) and press `ENTER`.
5. **Select Target Locations**:
   - Use `↑` / `↓` arrow keys and press **`SPACEBAR`** to tick `[✓]` all the locations you want (e.g., `Remote`, `Bengaluru`, `Hyderabad`, `Pune`, `Gurugram`, `Mumbai`, `Chennai`, `Delhi NCR`), then press `ENTER`.
6. **Select Job Portals to Search**:
   - Use **`SPACEBAR`** to tick `[✓]` `Greenhouse`, `Workday`, and `Lever`, then press `ENTER`.
7. **Live Demo Run**:
   - When asked `Would you like to run a live scan & send a test email right now? (y/n) [n]:`, type **`y`** and press `ENTER` to immediately receive your first email report!

---

## What Happens Automatically After Setup

- **11:00 AM Daily Email**: Every day at **11:00 AM**, the agent scans all selected portals and emails you only **new** jobs posted since your last check.
- **Closed / Switched-Off Laptop Wake-Up**: If your laptop is closed or turned off at 11:00 AM, as soon as you switch on or open your laptop later that day and Wi-Fi connects, the agent automatically wakes up, runs the missed scan once, and sends your email report.
- **Update Preferences Anytime**: Run `python setup_agent.py` again whenever you want to change your role or locations.
