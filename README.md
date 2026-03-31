# 🐻 B.E.A.R BOT

**Back-office Efficiency Agent & Ranking** — A Telegram bot for managing Twendee ERP operations.

## Features

### Feature 1: Tạo Đơn qua Telegram Bot
Create leave, overtime, business trip, and check-in applications directly through Telegram with a step-by-step conversation flow.

- `/taodon` — Start creating a new application
- `/donganday` — View your recent applications

### Feature 2: Duyệt Đơn qua Telegram
Approve or reject applications with inline buttons. Receive automatic notifications for new pending approvals.

- `/duyetdon` — View pending approvals
- Auto-notifications every 60 seconds for new pending applications

### Feature 3: Bot Tự Động Cắt Email & Tài Khoản ERP
Admin/HR can deactivate employee accounts when they offboard. Auto-detects approved offboarding applications.

- `/offboard <employee_code>` — Search and deactivate an employee account

### Feature 4: AI Report Agent (Gemini)
Ask the bot to generate reports using natural language. Powered by Google Gemini.

- `/report` — Start a conversation with the AI report agent
- Describe the report you need in plain language (Vietnamese or English)
- The agent will ask clarifying questions if needed, then fetch data and format a report

## Setup

### 1. Prerequisites
- Python 3.11+
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Access to the Twendee ERP staging API

### 2. Install Dependencies
```bash
cd erp-hack
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your values
```

Required variables:
| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `ERP_BASE_URL` | ERP API URL (default: `https://staging-erp.twendeesoft.com`) |
| `GEMINI_API_KEY` | Google AI Studio API key ([get one here](https://aistudio.google.com/apikey)) |

### 4. Run the Bot
```bash
python -m bot.main
```

## Authentication Flow

1. User sends `/login` to the bot
2. Bot sends a Google OAuth link to the ERP system
3. User authenticates in the browser
4. After successful auth, user copies the `access_token` from the response
5. User sends `/token <access_token>` to save it
6. Bot verifies the token and stores the session

## Architecture

```
bot/
├── main.py                      # Entry point, handler registration
├── config.py                    # Environment variables, constants
├── database.py                  # SQLite session storage
├── erp_client.py                # HTTP client for ERP API
├── ai/
│   ├── gemini_client.py         # Gemini API wrapper & tool definitions
│   └── report_agent.py          # AI report orchestration agent
├── auth/
│   └── handler.py               # /login, /token, /logout, /status
├── features/
│   ├── create_application.py    # Feature 1: Create applications
│   ├── approve_application.py   # Feature 2: Approve/reject
│   ├── account_management.py    # Feature 3: Offboard employees
│   └── ai_report.py             # Feature 4: AI report generation
└── utils/
    ├── keyboards.py             # Inline keyboard builders
    └── formatters.py            # Message formatters (Vietnamese)
```

## Commands

| Command | Description | Access |
|---|---|---|
| `/start` | Welcome + main menu | All |
| `/login` | Google OAuth login | All |
| `/token` | Save access token | All |
| `/logout` | Clear session | All |
| `/status` | Login status | All |
| `/taodon` | Create application | Authenticated |
| `/donganday` | Recent applications | Authenticated |
| `/duyetdon` | Pending approvals | Manager/HR/Admin |
| `/offboard` | Deactivate employee | HR/Admin |
| `/report` | AI report generation | Authenticated |
| `/help` | Command list | All |
| `/cancel` | Cancel current action | All |
