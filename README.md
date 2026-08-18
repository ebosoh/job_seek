# 🤖 Autonomous LinkedIn Job Search, Auto-Apply & Email Tracking Agent

An enterprise-grade autonomous AI Agent designed to find, score, and auto-apply for target remote AI and workflow engineering opportunities on LinkedIn using an authenticated Playwright browser session, and manage follow-ups and interview invites via email.

---

## 🎯 Key Capabilities

- **IILS (Interview Invitation Likelihood Score) Algorithm:** Evaluates opportunities based on skill match (40%), time posted (25%), applicant competition (20%), and title exactness (15%). Only auto-applies if $IILS \ge 70$.
- **Stealth & Persistent Browser Sessions:** Reuses persistent user profiles in `./sessions/linkedin_profile` to prevent CAPTCHA/2FA issues and mimic human interaction patterns.
- **Dynamic CV Parsing & Profile Synthesis:** Automatically parses candidate details, contact metadata, skills, and experience from `./data/Hudson E. Omunga- AI Engineer CV-2026.pdf` (or `.txt`).
- **Contextual Form-Filling & Question Answering:** Uses Google Gemini (or OpenAI) to generate tailored 2–3 sentence answers linking CV projects to specific job requirements with an $85\%$ confidence safety gate.
- **Multi-Step Easy Apply Automation:** Fills contact info, experience numbers, salary expectations, authorization radios, and attaches resume PDF.
- **Safe Dry-Run Mode:** Supports `--dry-run` to execute search, scoring, and form preparation up to the submit gate with visual screenshot logging.
- **Automated Email Monitoring & Recruiter Response Tracking:** Scans incoming messages at `hudson.eboso@techbrain.africa` via IMAP, classifies recruiter responses (`INTERVIEW_INVITE`, `ASSESSMENT_REQUEST`, `REJECTION`, `ACKNOWLEDGMENT`), and updates `./output/application_tracker.csv`.
- **Daily Performance Reporting:** Dispatches daily accomplishment reports and action items to `hudson.eboso@techbrain.africa` and saves to `./output/daily_reports/`.

---

## 📁 Project Architecture

```
job_seek/
├── agent.py                        # Unified CLI Orchestrator & Entry Point
├── main.py                         # Application alias
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
├── .env                            # Active environment configuration
├── .gitignore                      # Git ignore rules
│
├── data/                           # Candidate CV & Profile Storage
│   └── Hudson E. Omunga- AI Engineer CV-2026.txt
│
├── output/                         # Local Persistent Output Files
│   ├── application_tracker.csv     # Master application lifecycle database
│   ├── external_jobs_to_review.csv # Qualified non-Easy Apply jobs (IILS >= 80)
│   ├── daily_reports/              # Saved daily performance reports
│   └── screenshots/                # Dry-run application screenshots
│
├── sessions/                       # Persistent Playwright browser profile
│   └── linkedin_profile/
│
├── logs/                           # Runtime agent logs
│   └── agent.log
│
├── src/
│   ├── config.py                   # Pydantic configuration & environment settings
│   ├── core/
│   │   ├── cv_parser.py            # PDF/TXT Resume parser & skill extractor
│   │   ├── llm_client.py           # Gemini/OpenAI client & question answerer
│   │   └── matcher.py              # IILS algorithm & eligibility evaluator
│   ├── browser/
│   │   ├── stealth.py              # Anti-bot bypass scripts
│   │   ├── session_manager.py      # Persistent session & login manager
│   │   ├── job_scanner.py          # Search scraper & job card evaluator
│   │   └── easy_applier.py         # Multi-step Easy Apply form engine
│   ├── data/
│   │   └── tracker.py              # ApplicationTracker CSV manager
│   └── email_monitor/
│       ├── inbox_scanner.py        # IMAP email reader & response classifier
│       └── reporter.py             # Daily Accomplishment report generator
│
└── tests/                          # Automated unit & integration tests
    ├── test_cv_parser.py
    ├── test_matcher.py
    ├── test_llm_and_classifier.py
    └── test_tracker_and_reporter.py
```

---

## 🧮 The IILS Algorithm

$$IILS = (Match_{Skill} \times 0.40) + (Score_{Time} \times 0.25) + (Score_{Applicants} \times 0.20) + (Score_{Title} \times 0.15)$$

| Component | Weight | Scoring Logic |
| :--- | :---: | :--- |
| **Skill Match** | **40%** | Overlap between CV skills and job requirements. Minimum gate: $\ge 75\%$. |
| **Time Posted** | **25%** | $< 24\text{h} = 100\text{ pts}$, $24\text{--}48\text{h} = 75\text{ pts}$, $3\text{--}7\text{d} = 40\text{ pts}$, $> 7\text{d} = 0\text{ pts}$. |
| **Applicant Count** | **20%** | $< 25 = 100\text{ pts}$, $25\text{--}50 = 70\text{ pts}$, $51\text{--}100 = 40\text{ pts}$, $> 100 = 10\text{ pts}$. |
| **Title Exactness** | **15%** | Target list match $= 100\text{ pts}$, semantic close match $= 85\text{ pts}$, keywords $= 70\text{ pts}$. |

### Routing Decisions:
- **Easy Apply & $IILS \ge 70$:** $\longrightarrow$ Auto-applied & logged in `application_tracker.csv`.
- **Non-Easy Apply & $IILS \ge 80$:** $\longrightarrow$ Saved in `external_jobs_to_review.csv` for human review.
- **$IILS < 70$ or Geographic Mismatch:** $\longrightarrow$ Skipped.

---

## 🚀 Quick Start Guide

### 1. Install Dependencies & Playwright Browsers
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment (`.env`)
Edit `.env` with your API keys and credentials:
```env
# Candidate Details
CANDIDATE_NAME="Hudson E. Omunga"
CANDIDATE_EMAIL="hudson.eboso@techbrain.africa"
CANDIDATE_PHONE="+254727869396"
RESUME_PATH="data/Hudson E. Omunga- AI Engineer CV-2026.pdf"

# LLM (Gemini or OpenAI)
LLM_PROVIDER="gemini"
GEMINI_API_KEY="your-gemini-api-key"

# Email IMAP & SMTP Settings
IMAP_SERVER="mail.techbrain.africa"
IMAP_USERNAME="hudson.eboso@techbrain.africa"
IMAP_PASSWORD="your-email-password"
```

### 3. Place Resume
Ensure your PDF resume is saved in `./data/Hudson E. Omunga- AI Engineer CV-2026.pdf`.

### 4. Interactive LinkedIn Login (Run Once)
Launch the browser to log in to LinkedIn manually and save your persistent session:
```bash
python agent.py login
```
*Log into your LinkedIn account in the opened window. Once you reach the LinkedIn feed, your session is saved locally in `./sessions/linkedin_profile`.*

---

## 💻 CLI Commands

### 🔍 1. Scan & Score LinkedIn Jobs
Scans LinkedIn across all configured target roles and displays a rich table of opportunities scored by IILS without applying:
```bash
python agent.py scan --max 5
```

### 🎯 2. Run Auto-Apply in Dry-Run Mode (Safe Verification)
Prepares applications, navigates modal forms, generates LLM answers, and captures screenshot before submit:
```bash
python agent.py apply --dry-run
```

### 🚀 3. Run Auto-Apply in Live Mode
Finds, scores, and submits live Easy Apply applications:
```bash
python agent.py apply --live
```

### 📬 4. Monitor Email Inbox
Scans `hudson.eboso@techbrain.africa` for interview invitations, technical tests, or status updates:
```bash
python agent.py monitor-email
```

### 📊 5. Generate Daily Performance Report
Generates and prints the formatted accomplishment report:
```bash
python agent.py report
```

### 🌟 6. Run Complete Daily Cycle
Executes the full pipeline (Apply $\to$ Monitor Email $\to$ Generate Report):
```bash
python agent.py run-daily
```

### ⏰ 7. Start Daily Scheduler (18:00 Local Time)
Starts the agent background scheduler to execute the full cycle automatically every day at 18:00:
```bash
python agent.py schedule
```

---

## 🧪 Running Unit Tests
```bash
pytest tests/ -v
```

---

## 🔒 Security & Local Data Policy
All candidate details, browser cookies, sessions, application records, and screenshots are stored strictly on your **local computer disk** (`./data/`, `./sessions/`, `./output/`, `./logs/`). No sensitive credentials or session data are shared externally.
