import logging
from helpers.gitlabreviewhelper import ChatGPTReviewer, GitLabClient, get_diffs_from_mr, post_review_comments
from common.config_loader import GITLAB_URL, GITLAB_TOKEN, PROJECT_ID, MR_ID

def setup_logging():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

def main():
    # Setup logging
    setup_logging()
    logging.info("Starting GitLab review process...")

    # Initialize GitLab client and ChatGPT reviewer
    gl_client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    reviewer = ChatGPTReviewer()

    try:
        # Fetch diffs, MR, and latest diff details
        diffs, mr, latest_diff = get_diffs_from_mr(gl_client, PROJECT_ID, MR_ID)
        logging.info("Fetched diffs for the specified MR.")

        # Generate review comments
        review_comments = reviewer.get_review(diffs)
        logging.info("Generated review comments.")

        # Post review comments to GitLab
        error_message = post_review_comments(mr, review_comments, latest_diff)
        
        if error_message:
            logging.error(f"Failed to post some comments: {error_message}")
        else:
            logging.info("Successfully posted all review comments.")
    except Exception as e:
        logging.error(f"An error occurred during the review process: {e}")

if __name__ == "__main__":
    main()
