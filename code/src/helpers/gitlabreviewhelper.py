import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Tuple

import gitlab
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from common import (GITLAB_TOKEN, GITLAB_URL, MODEL, MR_ID, OPENAI_API_KEY,
                    PROJECT_ID, PROMPT_FILE, SKIP_EXTENSIONS, TOKEN_LIMIT)

logging.basicConfig(encoding='utf-8', level=logging.INFO)

@dataclass
class Diff:
    """Represents a file difference (diff) in a GitLab Merge Request.

    Attributes:
        oldpath (str): The path to the file in the previous version.
        newpath (str): The path to the file in the new version.
        parsed_lines (List[ParsedLine]): A list of parsed lines indicating the changes.
    """
    oldpath: str
    newpath: str
    parsed_lines: List['ParsedLine']

@dataclass
class ParsedLine:
    """Represents a single line within a diff, including its context in the code.

    Attributes:
        content (str): The actual content of the line.
        old_line (Optional[int]): The line number in the old version of the file (if present).
        new_line (Optional[int]): The line number in the new version of the file (if present).
        type (str): The type of change (e.g., 'added', 'deleted', 'unchanged').
    """
    content: str
    old_line: Optional[int]
    new_line: Optional[int]
    type: str

class ReviewComment(BaseModel):
    """Defines a comment for a code review, specifying the location and type of feedback.

    Attributes:
        Comment (str): The text content of the comment.
        Path (Optional[str]): The file path to which the comment applies.
        StartLine (int): The starting line of the code being commented on.
        EndLine (int): The ending line of the code being commented on.
        Type (str): The type of comment (e.g., 'suggestion', 'issue', 'notice').
    """
    Comment: str
    Path: Optional[str] = None
    StartLine: int
    EndLine: int
    Type: str

def retry_on_exception(max_retries=3, initial_delay=1, backoff_factor=2):
    """Decorator to retry a function on exception, with exponential backoff on rate limit errors."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    logging.error(f"Rate limit error: {e}. Attempt {attempt + 1} of {max_retries}. Retrying in {delay} seconds.")
                    time.sleep(delay)
                    delay *= backoff_factor  # Exponential backoff
                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed with error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= backoff_factor
            raise RuntimeError("Max retries reached. Unable to complete the request.")
        return wrapper
    return decorator

class GitLabClient:
    def __init__(self, url: str, token: str):
        self.client = gitlab.Gitlab(url=url, private_token=token)

    def get_project(self, project_id: str):
        """Retrieve a GitLab project by ID."""
        return self.client.projects.get(project_id)

class ChatGPTReviewer:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = MODEL
        
        self.prompt_message = self.load_prompt_message() 
        self.token_limit = TOKEN_LIMIT  # Max tokens allowed per request
        
        # Calculate token count of the prompt message and set max_tokens_per_chunk accordingly
        prompt_tokens = self.calculate_token_count(self.prompt_message)
        self.max_tokens_per_chunk = self.token_limit - prompt_tokens  # Leave room for prompt tokens
        
        self.token_stats = {"total_tokens": 0, "static_tokens": 0, "diff_tokens": 0}  # To store token usage
        self.token_stats["static_tokens"] = prompt_tokens

    def send_to_chatgpt(self, messages):
        """Send a chunk of messages to ChatGPT and return the response content."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=messages,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error during API request: {e}")
            raise e

    @staticmethod
    def load_prompt_message() -> str:
        """Load the prompt message from an external file and append static instructions."""

        DEFAULT_PROMPT_MESSAGE = "Act as a professional code reviewer and provide feedback on the given code."
        try:
            with open(PROMPT_FILE, "r") as file:
                prompt_message = file.read().strip()
                
                # Check if the file was read but is empty
                if not prompt_message:
                    logging.warning("Prompt file is empty. Using default prompt message.")
                    prompt_message = DEFAULT_PROMPT_MESSAGE
        
        except FileNotFoundError:
            logging.error("Prompt file not found. Using default prompt message.")
            prompt_message = DEFAULT_PROMPT_MESSAGE
        except Exception as e:
            logging.error(f"Error reading prompt file: {e}. Using default prompt message.")
            prompt_message = DEFAULT_PROMPT_MESSAGE

        # Append the static part with JSON instructions
        static_instructions = """
Output: Respond in JSON format with concise comments, don't be polite here. Each review item should be an object with fields "Path", "StartLine", "EndLine", "Type" and "Comment". Where "Type": "old" when commenting removals, and "Type": "new" when commenting additions. Join all items in an array:

[
  {"Path": "/path/to/file1", "StartLine": 132, "EndLine": 135, "Type": "old", "Comment": "Review comment 1"},
  {"Path": "/path/to/file2", "StartLine": 155, "EndLine": 165, "Type": "new", "Comment": "Review comment 2"},
  {"Path": "/path/to/fileN", "StartLine": 250, "EndLine": 255, "Type": "new", "Comment": "Review comment N"}
]
"""
        return prompt_message + static_instructions

    def calculate_token_count(self, text: str) -> int:
        """Calculate the token count of a given text for the specified model."""
        encoding = tiktoken.encoding_for_model(self.model)
        return len(encoding.encode(text))

    @retry_on_exception(max_retries=5, initial_delay=2, backoff_factor=2)
    def get_review(self, diffs: List[Diff], task_details: str = "") -> str:
        """Send multiline summarized diffs with full filenames to ChatGPT for review, handling large requests."""
        base_messages = [
            {
                "role": "system",
                "content": self.prompt_message
            }
        ]

        if task_details:
            base_messages.append({
                "role": "user",
                "content": f"Task Details: {task_details}"
            })

        # Check token count and split if necessary
        chunks = split_into_chunks(diffs, self.max_tokens_per_chunk, base_messages, model=self.model)
        logging.info(f"Split into {len(chunks)} chunks due to token limits.")

        # Process each chunk separately and collect results
        reviews = []

        for i, chunk in enumerate(chunks):
            diff_summary = summarize_diffs_multiline(chunk)
            messages = base_messages + [{"role": "user", "content": diff_summary}]
            logging.info(f"Processing chunk {i+1}/{len(chunks)}.")
            
            message_text = "\n".join([msg["content"] for msg in messages])
            self.token_stats["diff_tokens"] += self.calculate_token_count(diff_summary)
            self.token_stats["total_tokens"] += self.calculate_token_count(message_text)

            # Call the helper method to send the request to ChatGPT
            response_content = self.send_to_chatgpt(messages)
            reviews.append(response_content)
        
        return reviews

    def get_token_statistic(self) -> dict:
        """Accessor to retrieve the token statistics."""
        return self.token_stats

def estimate_tokens(messages, model="gpt-4"):
    encoding = tiktoken.encoding_for_model(model)
    return sum(len(encoding.encode(message["content"])) for message in messages)

def split_into_chunks(diffs, max_tokens_per_chunk, base_messages, model="gpt-4"):
    """Split diffs into chunks based on token limits."""
    chunks = []
    current_chunk = []
    current_tokens = estimate_tokens(base_messages, model=model)
    logging.info(f"Count of Tokens for Base Message: {current_tokens}")

    summ_of_diff_tokens=0

    for diff in diffs:
        diff_text = summarize_diffs_multiline([diff])
        diff_tokens = len(tiktoken.encoding_for_model(model).encode(diff_text))
        summ_of_diff_tokens += diff_tokens

        if current_tokens + diff_tokens > max_tokens_per_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = estimate_tokens(base_messages, model=model)

        current_chunk.append(diff)
        current_tokens += diff_tokens

    logging.info(f"Count of Tokens for DIFF: {summ_of_diff_tokens}")
    
    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def summarize_diffs_multiline(diffs: List[Diff]) -> str:
    """Summarize diffs in multiline format with full filenames."""
    diff_summary = []

    for diff in diffs:
        file_path = diff.newpath or diff.oldpath
        diff_summary.append(f"PATH: {file_path}")

        for line in diff.parsed_lines:
            line_number = line.new_line if line.new_line is not None else line.old_line
            line_type = {
                'none': "(*)",
                'old': "(-)",
                'new': "(+)",
                'block': ""
            }.get(line.type, "")
            diff_summary.append(f"{line_number} {line_type}: {line.content}")

        diff_summary.append("")

    return "\n".join(diff_summary)

def parse_diff_block(diff_block: str) -> List[ParsedLine]:
    """Parse a single diff block and calculate line numbers for old and new files, handling multiple blocks."""
    parsed_lines = []
    old_line, new_line = None, None

    for line in diff_block.splitlines():
        header_match = re.match(r"@@ -(\d+),\d+ \+(\d+)(?:,\d+)? @@", line)
        if header_match:
            old_line = int(header_match.group(1))
            new_line = int(header_match.group(2))
            continue

        if line.startswith(" "):  # Unchanged line
            parsed_lines.append(ParsedLine(content=line[1:], old_line=old_line, new_line=new_line, type='none'))
            old_line += 1
            new_line += 1
        elif line.startswith("-"):  # Line removed from old file
            parsed_lines.append(ParsedLine(content=line[1:], old_line=old_line, new_line=None, type='old'))
            old_line += 1
        elif line.startswith("+"):  # Line added to new file
            parsed_lines.append(ParsedLine(content=line[1:], old_line=None, new_line=new_line, type='new'))
            new_line += 1

    return parsed_lines

def get_diffs_from_mr(gl_client, project_id, mr_id) -> Tuple[List[Diff], Any, Any]:
    """Retrieve and parse the diffs from a GitLab Merge Request."""
    project = gl_client.get_project(project_id)
    mr = project.mergerequests.get(id=mr_id)
    diffs = mr.diffs.list()
    latest_diff = sorted(diffs, key=lambda diff: datetime.fromisoformat(diff.created_at.replace('Z', '+00:00')))[-1]
    latest_diff = mr.diffs.get(latest_diff.id)  # Retrieve full details of the latest diff

    parsed_diffs = []
    for change in latest_diff.diffs:
        file_extension = os.path.splitext(change.get("new_path", change.get("old_path", "")))[-1]
        if file_extension in SKIP_EXTENSIONS:
            logging.info(f"Skipping file with extension {file_extension}: {change.get('new_path')}")
            continue

        parsed_lines = parse_diff_block(change.get("diff"))
        parsed_diffs.append(Diff(
            oldpath=change.get("old_path"),
            newpath=change.get("new_path"),
            parsed_lines=parsed_lines
        ))
    return parsed_diffs, mr, latest_diff

def post_review_comments(mr, review_comments, latest_diff) -> Optional[str]:
    """
    Parse and post each review comment as a GitLab discussion on the Merge Request.
    Supports multi-part review comments.
    Returns an error message with details if there's a failure.
    """
    error_details = []

    # Ensure `review_comments` is a list and each part is iterable
    if isinstance(review_comments, int):
        logging.error("Unexpected integer received for review_comments; expected list of comments.")
        return "Invalid review_comments format; expected list of comments but got integer."

    # If review_comments is expected to be multi-part, each part should be an iterable
    if not isinstance(review_comments, list):
        logging.error("Expected review_comments to be a list, but got a non-list type.")
        return "Invalid review_comments format; expected a list."

    # Process each part of the review (assuming multi-part response)
    for part_index, part_comments in enumerate(review_comments, start=1):
        logging.info(f"Posting part {part_index} of review comments.")

        if part_comments.startswith("```json"):
            part_comments = part_comments[8:]  # Remove the first 7 characters (```json)
        if part_comments.endswith("```"):
            part_comments = part_comments[:-3]  # Remove the last 3 characters 
        try:
            part_comments = json.loads(part_comments)
        except json.JSONDecodeError:
            logging.error("Invalid JSON from ChatGPT response.")
            return "Invalid JSON format in ChatGPT response."

        # Validate that each `part_comments` is a list before processing
        if not isinstance(part_comments, list):
            logging.error(f"Expected part {part_index} to be a list of comments, but got {type(part_comments).__name__}")
            error_details.append(f"Part {part_index} is not a list of comments.")
            continue

        for comment_data in part_comments:
            try:
                comment = ReviewComment(**comment_data)  # Validate comment structure
            except ValidationError as e:
                logging.warning(f"Invalid comment data in part {part_index}: {e}")
                error_details.append({"part": part_index, "error": str(e)})
                continue

            # Post each comment to GitLab
            try:
                mr.discussions.create({
                    'body': comment.Comment,
                    'position': {
                        'base_sha': latest_diff.base_commit_sha,
                        'start_sha': latest_diff.start_commit_sha,
                        'head_sha': latest_diff.head_commit_sha,
                        'position_type': 'text',
                        'new_path' if comment.Type == "new" else 'old_path': comment.Path,
                        'new_line' if comment.Type == "new" else 'old_line': comment.EndLine
                    }
                })
            except gitlab.exceptions.GitlabCreateError as e:
                error_message = f"Error posting comment in part {part_index}: {e.error_message}"
                logging.error(error_message)
                error_details.append({
                    "part": part_index,
                    "comment": comment.Comment,
                    "Path": comment.Path,
                    "StartLine": comment.StartLine,
                    "EndLine": comment.EndLine,
                    "Type": comment.Type,
                    "Error": error_message
                })

    if error_details:
        # Return a summary of errors for debugging
        return f"Failed to post some comments due to errors: {json.dumps(error_details, indent=2)}"
    return None

def main():
    gl_client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    reviewer = ChatGPTReviewer()

    # Retrieve diffs, project, and the latest diff details
    diffs, mr, latest_diff = get_diffs_from_mr(gl_client, PROJECT_ID, MR_ID)

    # Generate a review using the summarized diffs with full filenames
    review_comments = reviewer.get_review(diffs)
    logging.info(f"Review Comments JSON: {review_comments}")

    # Post each review comment on the corresponding line in GitLab
    post_review_comments(mr, review_comments, latest_diff)

if __name__ == "__main__":
    main()
