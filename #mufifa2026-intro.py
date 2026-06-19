import re
import urllib.request
import urllib.error
import json

def check_github_pr_status(pr_url: str) -> dict:
    """
    Parses a GitHub pull request URL and checks if it is merged.
    Returns:
        dict: {
            "success": bool,
            "merged": bool,
            "error_message": str
        }
    """
    # Matches URLs like:
    # https://github.com/gtech-mulearn/mufifa-2026/pull/34
    match = re.search(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        return {
            "success": False,
            "merged": False,
            "error_message": "Invalid GitHub Pull Request URL format."
        }
    
    owner = match.group(1)
    repo = match.group(2)
    pr_number = match.group(3)
    
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "mufifa-2026-bot-verifier",
            "Accept": "application/vnd.github.v3+json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                # 'merged' is a boolean in GitHub Pull Request API response
                is_merged = data.get("merged", False)
                return {
                    "success": True,
                    "merged": is_merged,
                    "error_message": None
                }
            else:
                return {
                    "success": False,
                    "merged": False,
                    "error_message": f"GitHub API returned status code {response.status}."
                }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "success": False,
                "merged": False,
                "error_message": "Pull Request not found. Make sure the repository and PR number are correct and public."
            }
        elif e.code == 403:
            limit_remaining = e.headers.get("X-RateLimit-Remaining")
            if limit_remaining == "0":
                return {
                    "success": False,
                    "merged": False,
                    "error_message": "GitHub API rate limit exceeded. Please try again later."
                }
            return {
                "success": False,
                "merged": False,
                "error_message": "Access denied (HTTP 403). The repository might be private or restricted."
            }
        else:
            return {
                "success": False,
                "merged": False,
                "error_message": f"GitHub API error: {e.reason} (HTTP {e.code})"
            }
    except Exception as e:
        return {
            "success": False,
            "merged": False,
            "error_message": f"Failed to connect to GitHub API: {str(e)}"
        }

def validate_submission(message_content: str) -> dict:
    """
    Validates the #mufifa2026-intro submission.
    Returns a dict detailing the action to take:
        {
            "approved": bool,
            "reaction": str,
            "reply_message": str
        }
    """
    # Find github PR URL in the message content
    match = re.search(r"(https?://(?:www\.)?github\.com/[^\s]+)", message_content)
    if not match:
        return {
            "approved": False,
            "reaction": "🚩",
            "reply_message": "❌ Please include your GitHub Pull Request URL in the submission."
        }
    
    pr_url = match.group(1)
    status = check_github_pr_status(pr_url)
    
    if not status["success"]:
        return {
            "approved": False,
            "reaction": "🚩",
            "reply_message": f"❌ Error checking pull request: {status['error_message']}"
        }
    
    if status["merged"]:
        return {
            "approved": True,
            "reaction": "🏁",
            "reply_message": None
        }
    else:
        return {
            "approved": False,
            "reaction": "🚩",
            "reply_message": "❌ Please submit the link after your pull request has been merged/accepted only."
        }
