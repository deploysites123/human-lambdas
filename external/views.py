import copy

from django.conf import settings
from rest_framework.generics import CreateAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from user_handler.models import Organization
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q, F
import analytics
from workflow_handler.models import Workflow, Task
from workflow_handler.views import GetCompletedTaskView

from .serializers import TaskSerializer, CompletedExternalTaskSerializer


class GetExternalCompletedTaskView(GetCompletedTaskView):
    """
    External API View for getting all the Tasks
    """
    authentication_classes = (TokenAuthentication,)
    serializer_class = CompletedExternalTaskSerializer


class CreateTaskView(CreateAPIView):
    """
    External API View for creating Tasks
    """

    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = TaskSerializer

    def get_queryset(self):
        user = self.request.user
        organizations = Organization.objects.filter(user=user).all()
        workflows = Workflow.objects.filter(
            Q(organization__in=organizations)
            & Q(organization__pk=self.kwargs["org_id"])
        )
        return Task.objects.filter(
            Q(workflow__in=workflows) & Q(workflow__id=self.kwargs["workflow_id"])
        )

    def perform_create(self, serializer):
        workflow = Workflow.objects.filter(id=self.kwargs["workflow_id"]).first()
        if not settings.DEBUG:
            analytics.track(
                self.request.user.pk,
                "Task Create Attempt",
                {
                    "user_id": self.request.user.pk,
                    "user_email": self.request.user.email,
                    "org_id": self.request.user.current_organization_id,
                    "workflow_id": workflow.id,
                    "source": "API",
                },
            )
        if "inputs" not in self.request.data or not self.request.data["inputs"]:
            return Response(
                {"status_code": 400, "errors": [{"message": "No inputs"}]}, status=400,
            )
        formatted_inputs = []
        for w_input in workflow.inputs:
            task_input = copy.deepcopy(w_input)
            try:
                task_input["value"] = self.request.data["inputs"][w_input["id"]]
            except KeyError:
                return Response(
                    {
                        "status_code": 400,
                        "errors": [
                            {
                                "message": "Cannot find input with input id: {}".format(
                                    w_input["id"],
                                )
                            }
                        ],
                    },
                    status=400,
                )
            formatted_inputs.append(task_input)
        serializer.save(outputs=workflow.outputs, inputs=formatted_inputs)
        with transaction.atomic():
            workflow.n_tasks = F("n_tasks") + 1
            workflow.save()
        if not settings.DEBUG:
            analytics.track(
                self.request.user.pk,
                "Task Create Success",
                {
                    "user_id": self.request.user.pk,
                    "user_email": self.request.user.email,
                    "org_id": self.request.user.current_organization_id,
                    "workflow_id": workflow.id,
                    "source": "API",
                },
            )
