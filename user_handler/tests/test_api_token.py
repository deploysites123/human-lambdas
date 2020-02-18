from rest_framework.test import APITestCase
from rest_framework import status

from user_handler.models import User


class TestAPIToken(APITestCase):
    def setUp(self):
        user = User(name="foo", email="foo@bar.com")
        user.set_password("fooword")
        user.save()
        response = self.client.post(
            "/v1/users/token/", {"email": "foo@bar.com", "password": "fooword"}
        )
        self.access_token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.access_token)
        response = self.client.post(
            "/v1/users/api-token/", {"email": "foo@bar.com", "password": "fooword"}
        )
        self.token = response.data["token"]

    def test_token(self):
        response = self.client.post(
            "/v1/users/api-token/", {"email": "foo@bar.com", "password": "fooword"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response)
        self.assertEqual(self.token, response.data["token"])
