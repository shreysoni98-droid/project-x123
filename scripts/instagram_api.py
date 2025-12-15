import time
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InstagramAPI:
    BASE_URL = "https://graph.facebook.com/v21.0"

    def __init__(self, access_token, instagram_account_id):
        self.access_token = access_token
        self.instagram_account_id = instagram_account_id

    def _make_request(self, method, endpoint, params=None):
        url = f"{self.BASE_URL}/{endpoint}"
        params = params or {}
        params['access_token'] = self.access_token

        if method == 'GET':
            response = requests.get(url, params=params)
        else:
            response = requests.post(url, params=params)

        response.raise_for_status()
        return response.json()

    def create_media_container(self, image_url, caption="", media_type="feed"):
        endpoint = f"{self.instagram_account_id}/media"
        params = {'image_url': image_url}

        if media_type == "story":
            params['media_type'] = 'STORIES'
        elif caption:
            params['caption'] = caption

        result = self._make_request('POST', endpoint, params)
        return result.get('id')

    def check_container_status(self, container_id):
        params = {'fields': 'status_code'}
        result = self._make_request('GET', container_id, params)
        return result.get('status_code', 'UNKNOWN')

    def wait_for_container_ready(self, container_id, max_wait=60):
        start = time.time()
        while time.time() - start < max_wait:
            status = self.check_container_status(container_id)
            if status == 'FINISHED':
                return True
            if status in ['ERROR', 'EXPIRED']:
                return False
            time.sleep(2)
        return False

    def publish_container(self, container_id):
        endpoint = f"{self.instagram_account_id}/media_publish"
        params = {'creation_id': container_id}
        result = self._make_request('POST', endpoint, params)
        return result.get('id')

    def post_to_feed(self, image_url, caption=""):
        container_id = self.create_media_container(image_url, caption, "feed")
        if not self.wait_for_container_ready(container_id):
            return {'success': False, 'error': 'Container not ready'}
        media_id = self.publish_container(container_id)
        return {'success': True, 'media_id': media_id}

    def post_to_story(self, image_url):
        container_id = self.create_media_container(image_url, media_type="story")
        if not self.wait_for_container_ready(container_id):
            return {'success': False, 'error': 'Container not ready'}
        media_id = self.publish_container(container_id)
        return {'success': True, 'media_id': media_id}
