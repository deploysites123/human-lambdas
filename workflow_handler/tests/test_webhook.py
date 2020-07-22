import logging
import os

from rest_framework.test import APITestCase
from rest_framework import status

from workflow_handler.models import WorkflowHook, Workflow, Task
from user_handler.models import User, Organization, Notification


logger = logging.getLogger(__file__)

_CURRENT_DIR = os.path.dirname(__file__)


class TestWebhook(APITestCase):
    def setUp(self):
        self.preset_user_name = "foo"
        self.preset_user_email = "foo@bar.com"
        self.organization_name = "fooinc"
        self.preset_user_password = "foowordbar"
        notification = Notification()
        notification.save()

        user = User(
            name=self.preset_user_name,
            email=self.preset_user_email,
            notifications=notification,
        )
        user.set_password(self.preset_user_password)
        user.save()
        organization = Organization(name=self.organization_name)
        organization.save()
        self.org_id = organization.id
        organization.add_admin(user)
        response = self.client.post(
            "/v1/users/token",
            {"email": "foo@bar.com", "password": self.preset_user_password},
        )
        self.admin_access_token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_access_token)
        self.hook_url = "http://some.url.com"
        self.workflow_data = {
            "name": "foowf",
            "description": "great wf",
            "inputs": [{"id": "foo", "name": "foo", "type": "text"}],
            "outputs": [
                {
                    "id": "foo",
                    "name": "foo",
                    "type": "single-selection",
                    "single-selection": {"options": ["foo1", "bar1"]},
                }
            ],
            "webhook": {"target": self.hook_url},
        }
        response = self.client.post(
            "/v1/orgs/{}/workflows/create".format(self.org_id),
            self.workflow_data,
            format="json",
        )
        self.workflow_id = response.data["id"]

    def test_admin_webhook_creation(self):
        self.assertIsNotNone(WorkflowHook.objects.get(user__email="foo@bar.com"))

    def test_webhook_update(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_access_token)
        new_url = "http://someother.url.com"
        response = self.client.patch(
            "/v1/orgs/{0}/workflows/{1}".format(self.org_id, self.workflow_id),
            {"webhook": {"target": new_url}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["webhook"]["target"], new_url)
        self.assertEqual(
            WorkflowHook.objects.get(workflow__pk=self.workflow_id).target, new_url
        )

    def test_webhook_retrieve(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_access_token)
        response = self.client.get(
            "/v1/orgs/{0}/workflows/{1}".format(self.org_id, self.workflow_id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["webhook"]["target"], "http://some.url.com")

    def test_webhook_delete(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_access_token)
        response = self.client.patch(
            "/v1/orgs/{0}/workflows/{1}".format(self.org_id, self.workflow_id),
            {"webhook": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            WorkflowHook.objects.filter(workflow__pk=self.workflow_id).count(), 0
        )

    def test_webhook_endpoint(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_access_token)
        response = self.client.get(
            "/v1/orgs/{0}/workflows/{1}/webhook".format(self.org_id, self.workflow_id),
        )
        self.assertEqual(response.data["target"], self.hook_url)

        new_url = "http://someother.url.com"
        response = self.client.patch(
            "/v1/orgs/{0}/workflows/{1}/webhook".format(self.org_id, self.workflow_id),
            {"target": new_url},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["target"], new_url)
        self.assertEqual(
            WorkflowHook.objects.get(workflow__pk=self.workflow_id).target, new_url
        )

        response = self.client.delete(
            "/v1/orgs/{0}/workflows/{1}/webhook".format(self.org_id, self.workflow_id),
        )
        self.assertEqual(
            response.status_code, status.HTTP_204_NO_CONTENT, response.data
        )
        self.assertEqual(
            WorkflowHook.objects.filter(workflow__pk=self.workflow_id).count(), 0
        )

    def test_invalid_url(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_access_token)
        self.workflow_data = {
            "name": "bar2",
            "description": "great bar",
            "inputs": [{"id": "foo", "name": "foo", "type": "text"}],
            "outputs": [
                {
                    "id": "foo",
                    "name": "foo",
                    "type": "single-selection",
                    "single-selection": {"options": ["foo1", "bar1"]},
                }
            ],
            "webhook": {"target": "not valid"},
        }
        response = self.client.post(
            "/v1/orgs/{}/workflows/create".format(self.org_id),
            self.workflow_data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["errors"][0]["field"], "webhook-->target")

    def test_webhook_delete_and_recreate(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.admin_access_token)
        response = self.client.patch(
            "/v1/orgs/{0}/workflows/{1}".format(self.org_id, self.workflow_id),
            {"webhook": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            WorkflowHook.objects.filter(workflow__pk=self.workflow_id).count(), 0
        )
        new_url = "http://someother.url.com"
        response = self.client.patch(
            "/v1/orgs/{0}/workflows/{1}".format(self.org_id, self.workflow_id),
            {"webhook": {"target": new_url}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["webhook"]["target"], new_url)
        self.assertEqual(
            WorkflowHook.objects.get(workflow__pk=self.workflow_id).target, new_url
        )


class TestWebhookTasks(APITestCase):
    def setUserClient(self, email):
        response = self.client.post(
            "/v1/users/token", {"email": email, "password": "foowordbar"}
        )
        self.access_token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.access_token)

    def setUp(self):
        self.file_path = os.path.join(_CURRENT_DIR, "data", "test.csv")
        registration_data = {
            "email": "foo@bar.com",
            "password": "foowordbar",
            "organization": "fooInc",
            "is_admin": True,
            "name": "foo",
        }
        _ = self.client.post("/v1/users/register", registration_data)

        registration_data["email"] = "foojr@bar.com"
        _ = self.client.post("/v1/users/register", registration_data)
        registration_data["email"] = "foo@bar.com"

        self.org_id = Organization.objects.get(user__email="foo@bar.com").pk
        response = self.client.post(
            "/v1/users/token", {"email": "foo@bar.com", "password": "foowordbar"}
        )
        self.access_token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.access_token)

        workflow_data = {
            "name": "uploader",
            "description": "great wf",
            "inputs": [
                {"id": "Alpha", "name": "alpha", "type": "text"},
                {"id": "Beta", "name": "beta", "type": "text"},
                {"id": "Gamma", "name": "gamma", "type": "text"},
            ],
            "outputs": [
                {
                    "id": "foo",
                    "name": "foo",
                    "type": "single-selection",
                    "single-selection": {
                        "options": [
                            {"id": "foo2", "name": "foo2"},
                            {"id": "bar2", "name": "bar2"},
                        ],
                    },
                }
            ],
            "webhook": {"target": "https://en9sk43hft479.x.pipedream.net"},
        }
        _ = self.client.post(
            "/v1/orgs/{}/workflows/create".format(self.org_id),
            workflow_data,
            format="json",
        )
        self.workflow_id = Workflow.objects.get(name="uploader").id
        with open(self.file_path) as f:
            data = {"file": f}
            response = self.client.post(
                "/v1/orgs/{0}/workflows/{1}/upload".format(
                    self.org_id, self.workflow_id
                ),
                data=data,
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        workflow_data = {
            "name": "uploader2",
            "description": "great wf",
            "inputs": [
                {"id": "Alpha", "name": "alpha", "type": "text"},
                {"id": "Beta", "name": "beta", "type": "text"},
                {"id": "Gamma", "name": "gamma", "type": "text"},
            ],
            "outputs": [
                {
                    "id": "foo",
                    "name": "foo",
                    "type": "single-selection",
                    "single-selection": {
                        "options": [
                            {"id": "foo2", "name": "foo2"},
                            {"id": "bar2", "name": "bar2"},
                        ],
                    },
                }
            ],
            "webhook": {"target": "https://en9sk43hft479.x.pipedream.net"},
        }
        _ = self.client.post(
            "/v1/orgs/{}/workflows/create".format(self.org_id),
            workflow_data,
            format="json",
        )

    def test_complete_single_selection_task(self):
        workflow = Workflow.objects.get(id=self.workflow_id)
        tasks = Task.objects.filter(workflow=workflow).all()
        output_values = ["foo1", "bar1"]
        expected_outputs = workflow.outputs
        for output_value, task in zip(output_values, tasks):
            exp_output = next(item for item in expected_outputs if item["id"] == "foo")
            exp_output[exp_output["type"]]["value"] = output_value
            output_list = [
                {
                    "id": "foo",
                    "name": "foo",
                    "type": "single-selection",
                    "single-selection": {
                        "value": output_value,
                        "options": [
                            {"id": "foo2", "name": "foo2"},
                            {"id": "bar2", "name": "bar2"},
                        ],
                    },
                }
            ]
            data = {"inputs": task.inputs, "outputs": output_list}
            response = self.client.patch(
                "/v1/orgs/{0}/workflows/{1}/tasks/{2}".format(
                    self.org_id, self.workflow_id, task.id
                ),
                data=data,
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
            self.assertEqual("completed", response.data["status"])
            self.assertEqual(expected_outputs, response.data["outputs"])
            self.assertEqual("completed", Task.objects.get(id=task.id).status)

    def test_find_and_fire(self):
        workflow = Workflow.objects.get(pk=self.workflow_id)
        filters = {
            "event": "task.completed",
            "workflow": workflow,
        }
        hooks = WorkflowHook.objects.filter(**filters)
        self.assertEqual(len(hooks), 1)
