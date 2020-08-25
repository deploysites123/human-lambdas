import os
import copy

from rest_framework.test import APITestCase
from rest_framework import status

from workflow_handler.models import Task
from user_handler.models import Organization
from workflow_handler.tests import DATA_PATH


class TestTaskList(APITestCase):
    def setUp(self):
        registration_data = {
            "email": "foo@bar.com",
            "password": "foowordbar",
            "organization": "fooInc",
            "is_admin": True,
            "name": "foo",
        }
        _ = self.client.post("/v1/users/register", registration_data)
        self.org_id = Organization.objects.get(user__email="foo@bar.com").pk
        response = self.client.post(
            "/v1/users/token", {"email": "foo@bar.com", "password": "foowordbar"}
        )
        self.access_token = response.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.access_token)
        response = self.client.get("/v1/users/api-token",)
        self.token = response.data["token"]

        workflow_data = {
            "name": "uploader",
            "description": "great wf",
            "data": [
                {
                    "id": "news",
                    "name": "news",
                    "type": "text",
                    "layout": {},
                    "text": {"read-only": True},
                },
                {
                    "id": "type",
                    "name": "type",
                    "type": "text",
                    "layout": {},
                    "text": {"read-only": True},
                },
                {
                    "id": "foo",
                    "name": "foo",
                    "type": "single-selection",
                    "single-selection": {"options": ["foo1", "bar1"]},
                },
            ],
        }
        response = self.client.post(
            "/v1/orgs/{}/workflows/create".format(self.org_id),
            workflow_data,
            format="json",
        )
        self.workflow_id = response.data["id"]
        data_file = os.path.join(DATA_PATH, "dataset.csv")
        with open(data_file, encoding="ISO-8859-1") as f:
            data = {"file": f}
            response = self.client.post(
                "/v1/orgs/{0}/workflows/{1}/upload".format(
                    self.org_id, self.workflow_id
                ),
                data=data,
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.completed_tasks = 150
        for task in Task.objects.all()[: self.completed_tasks]:
            data = copy.deepcopy(task.data)
            for idata in data:
                if idata["id"] == "foo":
                    idata["single-selection"]["value"] = "bar1"
            response_data = {"data": data}

            _ = self.client.patch(
                "/v1/orgs/{0}/workflows/{1}/tasks/{2}".format(
                    self.org_id, self.workflow_id, task.pk
                ),
                data=response_data,
                format="json",
            )

    def test_list_completed_task(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token)
        response = self.client.get(
            "/orgs/{}/workflows/{}/tasks/completed".format(
                self.org_id, self.workflow_id
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data["tasks"]), 100, response.data)
        response = self.client.get(
            "/orgs/{}/workflows/{}/tasks/completed".format(
                self.org_id, self.workflow_id
            ),
            format="json",
            data={"limit": 50},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data["tasks"]), 50, response.data)
        for itask in response.data["tasks"]:
            self.assertEqual(itask["status"], "completed", itask)
        self.assertEqual(response.data["count"], self.completed_tasks, response.data)
        self.assertFalse("layout" in response.data["tasks"][0]["inputs"])
        self.assertEqual(type(response.data["tasks"][0]["data"]), dict)
        # self.assertEqual(type(response.data["tasks"][0]["outputs"]), dict)

    def test_existing_workflow(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token)
        response = self.client.get(
            "/orgs/{}/workflows/{}/tasks/completed".format(
                self.org_id, self.workflow_id
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_existing_workflow(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token)
        response = self.client.get("/v1/orgs/10000/workflows/1000/completed")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_hook_serializer(self):
        task = Task.objects.filter(status="completed").first()
        result = task.serialize_hook()
        self.assertEqual(result["id"], task.pk)
        self.assertEqual(type(result["data"]), dict)
