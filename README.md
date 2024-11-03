# GitLab Auto (based on ChatGPT API) Review with Telegram Bot

This project provides a Review Helper script that interacts with GitLab to perform automated code reviews on Merge Requests (MRs) using OpenAI's ChatGPT. And Telegram Bot,  that can be invoked via Telegram messages or commands to review MRs based on specific rules and guidelines.

## Table of Contents
- [Features](#features)
- [Setup](#setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Running the Bot as a Service](#running-the-bot-as-a-service)
- [Troubleshooting](#troubleshooting)

## Features
- Automatically reviews GitLab Merge Requests with ChatGPT based on your coding guidelines.
- Allows usage of Telegram bot commands to request reviews.
- Supports multi-part reviews for large MRs that exceed API token limits.
- Configurable file extension filtering to skip unnecessary files.
- Logs errors and retries requests on rate limiting with exponential backoff.

## Setup

### Project Structure

```
src/
├── bots/                     # Telegram bot and handlers
│   └── tg_bot.py             # Main bot script to interact with users on Telegram
├── common/                   # Common modules
│   └── config_loader.py      # Loading configuration from ENV or config.ini
├── config/                   # Configuration files
│   ├── config.ini            # Configuration settings (tokens, URLs, etc.)
│   └── prompt.txt            # Custom prompt message for ChatGPT API
├── helpers/                  # Helper modules
│   └── gitlabreviewhelper.py # GitLab and ChatGPT integration for review automation
└── main.py                   # Main entry point
setup.py                      # Installation script
```

### Requirements
- **Python 3.8+**
- Python libraries: `python-dotenv`, `python-telegram-bot`, `gitlab`, `tiktoken`, `openai`, `pydantic`
- Access to a GitLab instance and a Telegram bot token from [BotFather](https://core.telegram.org/bots#botfather)

### Installation
1. **Clone the Repository**
   ```bash
   git clone https://github.com/MayVortex/gitlab_ai_reviewer .
   cd code
   ```
2. *** all in one prepare ***
   ```bash
   pip install -e .
   ```
   
   - Update `src/config/config.ini` with the necessary API keys, GitLab information, and model settings.
   - Customize the `prompt.txt` in the `config` folder for any specific instructions for the ChatGPT model.

-- OR --
3. **Set up a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate
   # venv\Scripts\activate # For Windows
   ```

4. **Configure environment variables and configuration files:**

   - Update `src/config/config.ini` with the necessary API keys, GitLab information, and model settings.
   - Customize the `prompt.txt` in the `config` folder for any specific instructions for the ChatGPT model.

5. **Install Dependencies**

   ```bash
   python setup.py install
   ```

## Configuration

All configuration options can be specified in the `config.ini` file or as environment variables.

### `config.ini`
Use `config.ini` for more persistent configurations.

```ini
[settings]
TELEGRAM_TOKEN = your_telegram_bot_token
GITLAB_URL = https://gitlab.yourdomain.com
GITLAB_TOKEN = your_gitlab_token
OPENAI_API_KEY = your_openai_api_key
PROJECT_ID = your_gitlab_project_id
MODEL = gpt-4o
SKIP_EXTENSIONS = .md, .txt  # Optional: Skip files with these extensions
PROMPT_FILE = /your/path/to/prompt.txt
```

### Configuration Parameters

| Parameter          | Description                                                                                                                                                    |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `TELEGRAM_TOKEN`   | Telegram bot token, required to interact with Telegram API.                                                                                                    |
| `GITLAB_URL`       | URL to the GitLab instance.                                                                                                                                   |
| `GITLAB_TOKEN`     | Private GitLab token for API access.                                                                                                                          |
| `OPENAI_API_KEY`   | API key for OpenAI's ChatGPT API.                                                                                                                             |
| `PROJECT_ID`       | GitLab project ID to pull and review MRs.                                                                                                                     |
| `MODEL`            | OpenAI model to use for reviews (default: `gpt-4`).                                                                                                           |
| `SKIP_EXTENSIONS`  | Comma-separated list of file extensions to skip (e.g., `.md, .txt`).                                                                                          |
| `PROMPT_FILE`  | Path to prompt (/your/path/to/prompt.txt                                                                                                                      |

## Usage

### Single start

```bash
gitlab_ai_reviewer_start
```

### Starting the Bot

```bash
gitlab_ai_reviewer_bot
```

### Bot Commands

The bot recognizes two types of messages:
1. /review
- **Direct Commands**: `/review <MR_ID>`
  - Example: `/review 1234`
- **Direct Commands**: `/review <MR_ID>: [task title and description]`
  - Example: `/review 1234: Update API endpoints`
2. /review@your_bot_name
- **Direct Commands**: `/review <MR_ID>`
  - Example: `/review@your_bot_name 1234`
- **Direct Commands**: `/review <MR_ID>: [task title and description]`
  - Example: `/review@your_bot_name 1234: Update API endpoints`
3. @botusername
- **Mentions in Group**: `@botusername <MR_ID>`
  - Example: `@botusername 1234`
- **Mentions in Group**: `@botusername <MR_ID> [task title and description]`
  - Example: `@botusername 1234: Fix logging issue`

The bot will process these commands, review the MR in GitLab, and respond with results.

## Running the Bot as a Service

To run the bot as a service, create a `systemd` service file:

```ini
# /etc/systemd/system/gitlab-review-bot.service
[Unit]
Description=GitLab Review Bot Service
After=network.target

[Service]
Type=simple
# If using system Python (pip install -e .) - use this:
ExecStart=/usr/local/bin/gitlab_ai_reviewer_bot

# Else - Path to your Python virtual environment (or system Python if not using a venv)
# ExecStart=/path/to/your/venv/bin/gitlab_ai_reviewer_bot

# Set the working directory to the project directory (optional)
# WorkingDirectory=/path/to/your/project

# Optional: Environment variables can be set here if needed
Environment=PYTHONUNBUFFERED=1
# Environment=TELEGRAM_TOKEN=your_telegram_token_here
# Environment=GITLAB_TOKEN=your_gitlab_token_here
# ...
Restart=on-failure
User=your_username  # Replace with your username
Group=your_group    # Replace with your user group

[Install]
WantedBy=multi-user.target
```

Then, enable and start the service:

```bash
sudo systemctl start gitlab_ai_reviewer_bot
sudo systemctl enable gitlab_ai_reviewer_bot

sudo systemctl status gitlab_ai_reviewer_bot
journalctl -u gitlab_ai_reviewer_bot -f
```

## Troubleshooting

### Common Errors

- **Rate Limiting**: If you see `RateLimitError`, the script will retry with exponential backoff. You may need to wait a few minutes.
- **Invalid Configurations**: If you encounter missing configuration errors, verify `.env` and `config.ini` for correctness.
- **Unexpected Output or No Review**: Check logs for detailed error messages. Make sure `review_comments` is correctly formatted as a list before calling `post_review_comments`.

### Logging

Logs are stored in `tg-bot.log` (if enabled) and contain detailed information about the bot's operations.

```python
# Example to enable file logging
logging.basicConfig(filename="tg-bot.log", level=logging.INFO)
```

## Contributing

Feel free to open issues, create pull requests, or suggest enhancements to improve the bot's functionality.

---

This bot simplifies GitLab Merge Request reviews by automating the process with ChatGPT, making code quality management seamless for your team.
