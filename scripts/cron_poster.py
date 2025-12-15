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

SCHEDULE_FILE = 'schedule.json'


def load_schedule():
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return {'posts': []}


def save_schedule(schedule):
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedule, f, indent=2)


def delete_image_from_github(image_url):
    """Delete image from GitHub after posting"""
    github_token = os.environ.get('GITHUB_TOKEN')
    repo_owner = os.environ.get('GITHUB_REPO_OWNER')
    repo_name = os.environ.get('GITHUB_REPO_NAME')

    if not all([github_token, repo_owner, repo_name]):
        logger.warning("GitHub credentials not available for image cleanup")
        return False

    try:
        # Extract filename from URL
        if 'raw.githubusercontent.com' in image_url:
            filename = image_url.split('/images/')[-1]
            repo_path = f"images/{filename}"
        else:
            return False

        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        # Get file SHA
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{repo_path}"
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            logger.warning(f"Image not found in repo: {repo_path}")
            return False

        sha = response.json().get('sha')

        # Delete file
        data = {
            'message': f'Auto-delete after posting: {filename}',
            'sha': sha,
            'branch': 'main'
        }

        response = requests.delete(url, headers=headers, json=data)

        if response.status_code == 200:
            logger.info(f"Deleted image from GitHub: {repo_path}")
            return True
        else:
            logger.warning(f"Failed to delete image: {response.json()}")
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

    api = InstagramAPI(token, account_id)
    schedule = load_schedule()
    now = datetime.now()

    logger.info(f"Checking schedule at {now}")
    logger.info(f"Total posts in schedule: {len(schedule.get('posts', []))}")

    posts_published = 0
    images_to_delete = []

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
                    post['status'] = 'posted'
                    post['posted_at'] = now.isoformat()
                    post['media_id'] = result.get('media_id')
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

    schedule['last_checked'] = now.isoformat()
    save_schedule(schedule)

    # Delete images after successful posting
    for image_url in images_to_delete:
        delete_image_from_github(image_url)

    logger.info(f"Done. Published {posts_published} posts.")


if __name__ == "__main__":
    main()
