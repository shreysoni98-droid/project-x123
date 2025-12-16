import os
import sys
import json
import base64
import logging
import requests
from datetime import datetime

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from instagram_api import InstagramAPI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# GitHub configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO_OWNER = os.environ.get('GITHUB_REPO_OWNER')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPO_NAME')

GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
GITHUB_HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}


def get_schedule_from_github():
    """Get schedule.json from GitHub via API"""
    try:
        url = f"{GITHUB_API_BASE}/contents/schedule.json"
        response = requests.get(url, headers=GITHUB_HEADERS)

        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data['content']).decode('utf-8')
            sha = data['sha']
            return json.loads(content), sha
        else:
            logger.error(f"Failed to get schedule.json: {response.status_code}")
            return {'posts': []}, None
    except Exception as e:
        logger.error(f"Error getting schedule from GitHub: {e}")
        return {'posts': []}, None


def update_schedule_on_github(schedule, sha):
    """Update schedule.json on GitHub via API"""
    try:
        url = f"{GITHUB_API_BASE}/contents/schedule.json"
        content = base64.b64encode(json.dumps(schedule, indent=2).encode()).decode()

        data = {
            'message': 'Update schedule after posting',
            'content': content,
            'sha': sha,
            'branch': 'main'
        }

        response = requests.put(url, headers=GITHUB_HEADERS, json=data)

        if response.status_code == 200:
            logger.info("Updated schedule.json on GitHub")
            return True
        else:
            logger.error(f"Failed to update schedule.json: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error updating schedule on GitHub: {e}")
        return False


def delete_image_from_github(image_url):
    """Delete image from GitHub via API"""
    try:
        # Extract filename from URL
        if 'raw.githubusercontent.com' in image_url:
            filename = image_url.split('/images/')[-1]
            repo_path = f"images/{filename}"
        else:
            logger.warning(f"Invalid image URL format: {image_url}")
            return False

        # Get file SHA
        url = f"{GITHUB_API_BASE}/contents/{repo_path}"
        response = requests.get(url, headers=GITHUB_HEADERS)

        if response.status_code != 200:
            logger.warning(f"Image not found in repo: {repo_path}")
            return False

        sha = response.json().get('sha')

        # Delete file
        data = {
            'message': f'Delete after posting: {filename}',
            'sha': sha,
            'branch': 'main'
        }

        response = requests.delete(url, headers=GITHUB_HEADERS, json=data)

        if response.status_code == 200:
            logger.info(f"Deleted image from GitHub: {repo_path}")
            return True
        else:
            logger.error(f"Failed to delete image: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error deleting image: {e}")
        return False


def main():
    token = os.environ.get('INSTAGRAM_ACCESS_TOKEN')
    account_id = os.environ.get('INSTAGRAM_ACCOUNT_ID')

    if not token or not account_id:
        logger.error("Missing INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID")
        return

    if not all([GITHUB_TOKEN, GITHUB_REPO_OWNER, GITHUB_REPO_NAME]):
        logger.error("Missing GitHub configuration")
        return

    api = InstagramAPI(token, account_id)

    # Get schedule from GitHub
    schedule, schedule_sha = get_schedule_from_github()

    if schedule_sha is None:
        logger.error("Could not get schedule from GitHub")
        return

    now = datetime.now()

    logger.info(f"Checking schedule at {now}")
    logger.info(f"Total posts in schedule: {len(schedule.get('posts', []))}")

    posts_published = 0
    images_to_delete = []
    posted_ids = []  # Track IDs of successfully posted entries to remove

    for post in schedule.get('posts', []):
        if post.get('status') != 'pending':
            continue

        scheduled_time = post.get('scheduled_time', '')
        if not scheduled_time:
            continue

        try:
            post_time = datetime.strptime(scheduled_time, '%Y-%m-%d %H:%M')
            if post_time <= now:
                logger.info(f"Publishing post: {post.get('id')}")

                image_url = post.get('image_url', '')
                caption = post.get('caption', '')
                post_type = post.get('post_type', 'feed')

                if post_type == 'story':
                    result = api.post_to_story(image_url)
                else:
                    result = api.post_to_feed(image_url, caption)

                if result['success']:
                    posted_ids.append(post.get('id'))
                    posts_published += 1
                    logger.info(f"Posted successfully: {result.get('media_id')}")

                    # Queue image for deletion
                    if image_url:
                        images_to_delete.append(image_url)
                else:
                    post['status'] = 'failed'
                    post['error'] = result.get('error')
                    logger.error(f"Failed: {result.get('error')}")

        except ValueError as e:
            logger.error(f"Invalid date format: {e}")

    # Remove successfully posted entries from schedule
    if posted_ids:
        schedule['posts'] = [p for p in schedule.get('posts', []) if p.get('id') not in posted_ids]
        logger.info(f"Removed {len(posted_ids)} posted entries from schedule")

    schedule['last_checked'] = now.isoformat()

    # Update schedule on GitHub if changed
    if posted_ids or any(p.get('status') == 'failed' for p in schedule.get('posts', [])):
        update_schedule_on_github(schedule, schedule_sha)

    # Delete images from GitHub after successful posting
    for image_url in images_to_delete:
        delete_image_from_github(image_url)

    logger.info(f"Done. Published {posts_published} posts.")


if __name__ == "__main__":
    main()
