"""
Telegram Bot to review GitLab Merge Requests using ChatGPT

This script sets up a Telegram bot that allows users to request reviews for GitLab Merge Requests (MRs) via the `/review` command or by mentioning the bot with an MR ID.
The bot retrieves the MR diffs, sends them for review using a ChatGPT-based reviewer, and posts the review comments back to the GitLab MR.

Modules:
- telegram: Handles bot interaction with Telegram API.
- asyncio: Provides asynchronous features.
- logging: Provides logging facilities.
- re: Provides regular expression operations.
- common: Custom module containing shared configuration variables.
- helpers: Custom module containing helper classes and functions.

Functions:
- review_merge_request_async(mr_id: int, task_details: str) -> str: Asynchronously processes a merge request and returns the result message.
- start(update: Update, context: ContextTypes.DEFAULT_TYPE): Command handler for the `/start` command.
- review_command(update: Update, context: ContextTypes.DEFAULT_TYPE): Command handler for the `/review` command.
- handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE): Handles messages containing MR IDs addressed to the bot.
- error_handler(update: object, context: ContextTypes.DEFAULT_TYPE): Logs any exceptions raised during updates.
- set_bot_commands(application: Application): Sets bot commands for the Telegram menu.
- main(): Entry point for running the bot.
- run_bot(): Asynchronously runs the bot with custom retry logic.

Usage:
- Use `/start` to see the welcome message.
- Use `/review MR_ID` to request a review for an MR.
- Use `/review MR_ID: task title and description` to provide additional task details.
- Mention the bot with an MR ID in a group to start a review.

"""

import asyncio
import logging
import re

from common import GITLAB_TOKEN, GITLAB_URL, PROJECT_ID, TELEGRAM_TOKEN
from helpers import (ChatGPTReviewer, GitLabClient, get_diffs_from_mr,
                     post_review_comments)
from telegram import BotCommand, Update
from telegram.error import NetworkError
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def review_merge_request_async(mr_id: int, task_details: str = "") -> str:
    """
    Asynchronously processes a GitLab Merge Request and generates a review.

    Args:
        mr_id (int): The Merge Request ID.
        task_details (str): Optional task title and description to provide context for the review.

    Returns:
        str: A message indicating the result of the review process.
    """
    try:
        gl_client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
        reviewer = ChatGPTReviewer()

        diffs, mr, latest_diff = get_diffs_from_mr(gl_client, PROJECT_ID, mr_id)

        # Include task details in the review process if provided
        review_comments = await asyncio.to_thread(reviewer.get_review, diffs, task_details=task_details)

        # Retrieve the token statistics after the review is generated
        token_stats = reviewer.get_token_statistic()

        # Attempt to post review comments
        error_message = await asyncio.to_thread(post_review_comments, mr, review_comments, latest_diff)

        # Build token usage summary
        token_summary = f"""
            Total tokens: {token_stats['total_tokens']}
            Static tokens: {token_stats['static_tokens']}
            Diff tokens: {token_stats['diff_tokens']}
        """

        if error_message:
            return f"Review completed with errors for MR ID {mr_id}:\n{error_message}"
        return f"Review completed and comments posted for Merge Request ID: {mr_id}\n\n{token_summary}"

    except Exception as e:
        logging.error(f"Error processing MR ID {mr_id}: {e}")
        return f"Failed to process Merge Request ID: {mr_id}. Error: {e}\nTask Details: {task_details}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the `/start` command and sends a welcome message to the user.

    Args:
        update (Update): Incoming update from Telegram.
        context (ContextTypes.DEFAULT_TYPE): Bot's context.
    """
    await update.message.reply_text(
        "Welcome! Use /review followed by MR ID and optionally a task title and description to submit a review request."
    )

async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the `/review` command to initiate the review process for a GitLab Merge Request.

    Args:
        update (Update): Incoming update from Telegram.
        context (ContextTypes.DEFAULT_TYPE): Bot's context.
    """
    # Extract the message text after the /review command
    message_text = update.message.text.strip()

    # Match the format /review MR_ID or /review MR_ID: task title and description
    pattern_with_details = r"^/review(?:.+|)\s+(\d+):\s*(.*)"
    pattern_without_details = r"^/review(?:.+)\s+(\d+)$"

    match_with_details = re.search(pattern_with_details, message_text)
    match_without_details = re.search(pattern_without_details, message_text)

    # Determine the format of the message and extract data accordingly
    if match_with_details:
        mr_id = int(match_with_details.group(1))  # Extract the MR ID
        task_details = match_with_details.group(2)  # Extract the task title and description

    elif match_without_details:
        mr_id = int(match_without_details.group(1))  # Extract the MR ID
        task_details = ""  # No task details provided

    else:
        await update.message.reply_text(
            "Invalid format. Use /review MR_ID or /review MR_ID: task title and description."
        )
        return

    # Start the review process with or without task details
    try:
        await update.message.reply_text(f"Received MR ID {mr_id}. Starting review...")
        result_message = await review_merge_request_async(mr_id, task_details=task_details)
        await update.message.reply_text(result_message)

    except Exception as e:
        logging.error(f"Error processing /review command: {e}")
        await update.message.reply_text(f"An error occurred while processing your request. Error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages containing MR IDs addressed to the bot in group chats.

    Args:
        update (Update): Incoming update from Telegram.
        context (ContextTypes.DEFAULT_TYPE): Bot's context.
    """
    # Ensure update.message and update.message.text are not None
    if not update.message or not update.message.text:
        logging.warning("Received a non-text message or an unsupported update type.")
        return

    bot_username = context.bot.username
    message_text = update.message.text.strip()

    # Check if the message matches either format
    pattern_with_details = rf"@{bot_username}\s+(\d+):\s*(.*)"
    pattern_without_details = rf"@{bot_username}\s+(\d+)"

    match_with_details = re.search(pattern_with_details, message_text)
    match_without_details = re.search(pattern_without_details, message_text)

    # Determine the format of the message and extract data accordingly
    if match_with_details:
        mr_id = int(match_with_details.group(1))  # Extract the MR ID
        task_details = match_with_details.group(2)  # Extract the task title and description

    elif match_without_details:
        mr_id = int(match_without_details.group(1))  # Extract the MR ID
        task_details = ""  # No task details provided

    else:
        logging.info("Message did not match expected format, ignoring.")
        return

    # Start the review process with or without task details
    try:
        await update.message.reply_text(f"Received MR ID {mr_id}. Starting review...")
        result_message = await review_merge_request_async(mr_id, task_details=task_details)
        await update.message.reply_text(result_message)

    except Exception as e:
        logging.error(f"Error processing message in group chat: {e}")
        await update.message.reply_text("An error occurred while processing your request. Please try again later.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Logs exceptions raised while handling updates.

    Args:
        update (object): The update that caused the error.
        context (ContextTypes.DEFAULT_TYPE): Bot's context.
    """
    logging.error(msg="Exception while handling an update:", exc_info=context.error)

async def set_bot_commands(application: Application) -> None:
    """
    Sets bot commands for the Telegram bot.

    Args:
        application (Application): The bot application instance.
    """
    commands = [
        BotCommand("review", "Submit a task for review"),
        BotCommand("start", "Start the bot and see welcome message"),
    ]
    await application.bot.set_my_commands(commands)

def main() -> None:
    """
    Entry point for running the bot.
    """
    asyncio.run(run_bot())

async def run_bot():
    """
    Asynchronously runs the bot and manages retry logic in case of network issues.
    """
    retry_delays = [3, 10, 30, 180]
    max_delay = 180
    retry_counter = 0

    application = Application.builder().token(TELEGRAM_TOKEN).post_init(set_bot_commands).build()

    # Set up command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("review", review_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    await application.initialize()
    await application.updater.start_polling(drop_pending_updates=True)
    await application.start()

    while True:
        try:
            # Keep the bot running
            await asyncio.Event().wait()
        except NetworkError as e:
            if retry_counter < len(retry_delays):
                delay = retry_delays[retry_counter]
            else:
                delay = max_delay
            logging.error(f"NetworkError occurred: {e}. Retrying in {delay} seconds.")
            await application.stop()
            await asyncio.sleep(delay)
            await application.start()
            retry_counter += 1
        except Exception as e:
            logging.error(f"An unexpected exception occurred: {e}")
            await asyncio.sleep(5)
        else:
            # Reset retry counter on successful run
            retry_counter = 0

if __name__ == "__main__":
    main()
