import requests
from django.conf import settings

class APIClient:
    API_BASE_URL = 'http://localhost:5000/api'

    @staticmethod
    def get_blogs(token=None):
        headers = APIClient._get_headers(token)
        return APIClient._make_request('GET', '/blogs', headers=headers)

    @staticmethod
    def get_blog_comments(blog_id, token=None):
        headers = APIClient._get_headers(token)
        return APIClient._make_request('GET', f'/blogs/{blog_id}/comments', headers=headers)

    @staticmethod
    def register_user(username, password):
        data = {'username': username, 'password': password}
        return APIClient._make_request('POST', '/register', json=data)

    @staticmethod
    def login_user(username, password):
        data = {'username': username, 'password': password}
        return APIClient._make_request('POST', '/login', json=data)

    @staticmethod
    def get_user_profile(token):
        headers = APIClient._get_headers(token)
        return APIClient._make_request('GET', '/profile', headers=headers)

    @staticmethod
    def update_user_profile(token, **profile_data):
        headers = APIClient._get_headers(token)
        return APIClient._make_request('PUT', '/profile', headers=headers, json=profile_data)

    @staticmethod
    def delete_blog(blog_id, token=None):
        """Delete a blog post from the Flask API."""
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        
        try:
            response = requests.delete(
                f'{APIClient.API_BASE_URL}/blogs/{blog_id}',
                headers=headers
            )
            return None, response.status_code
        except requests.RequestException as e:
            return {'error': str(e)}, 500

    @staticmethod
    def _get_headers(token=None):
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        return headers

    @staticmethod
    def _make_request(method, endpoint, **kwargs):
        url = f'{APIClient.API_BASE_URL}{endpoint}'
        try:
            response = requests.request(method, url, **kwargs)
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500