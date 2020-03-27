from django.utils import timezone
from django.conf import settings
from rest_framework.generics import (
    CreateAPIView,
    RetrieveUpdateAPIView,
    ListAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from user_handler.models import Organization
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView
from rest_framework.response import Response
from workflow_handler.csv2task import process_csv
from django.db import transaction
from django.db.models import Q, F
from django.shortcuts import get_object_or_404, get_list_or_404
from rest_framework.pagination import LimitOffsetPagination
from user_handler.permissions import IsOrgAdmin

from .serializers import WorkflowSerializer, TaskSerializer
from .models import Workflow, Task


class CreateWorkflowView(CreateAPIView):
    permission_classes = (IsAuthenticated, IsOrgAdmin)
    serializer_class = WorkflowSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)


class ListWorkflowView(ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = WorkflowSerializer

    def get_queryset(self):
        user = self.request.user
        organizations = Organization.objects.filter(user=user).all()
        return Workflow.objects.filter(
            Q(disabled=False)
            & Q(organization__in=organizations)
            & Q(organization__pk=self.kwargs["org_id"])
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class RUDWorkflowView(RetrieveUpdateAPIView):
    """
    Retrieve and Update for now, will add delete here later
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = WorkflowSerializer

    def get_serializer(self, *args, **kwargs):
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        serializer_class = self.get_serializer_class()
        kwargs["context"] = self.get_serializer_context(*args, **kwargs)
        return serializer_class(*args, **kwargs)

    def get_serializer_context(self, *args, **kwargs):
        """
        Extra context provided to the serializer class.
        """
        context = {
            "request": self.request,
            "format": self.format_kwarg,
            "view": self,
        }
        try:
            if not kwargs["data"]["webhook"]:
                context["remove_webhook"] = not kwargs["data"].pop("webhook")
        except KeyError:
            pass
        return context

    def get_queryset(self):
        user = self.request.user
        organizations = Organization.objects.filter(user=user).all()
        return Workflow.objects.filter(
            Q(organization__in=organizations)
            & Q(organization__pk=self.kwargs["org_id"])
            & Q(pk=self.kwargs["workflow_id"])
        )

    def get_object(self):
        obj = get_object_or_404(self.get_queryset(), id=self.kwargs["workflow_id"])
        return obj

    def retrieve(self, request, *args, **kwargs):
        obj = get_object_or_404(self.get_queryset())
        workflow = self.serializer_class(obj).data
        if hasattr(obj, "workflowhook"):
            workflow["webhook"] = {"target": obj.workflowhook.target}
        return Response(workflow)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if instance.organization.admin.filter(pk=request.user.pk).exists():
            serializer = self.get_serializer(
                instance, data=request.data, partial=partial
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        return Response(
            {
                "status_code": 403,
                "errors": [
                    {"message": "You do not have permission to change workflow"}
                ],
            },
            status=403,
        )


def decode_utf8(input_iterator):
    for line in input_iterator:
        yield line.decode("utf-8")


class FileUploadView(APIView):

    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        file_obj = request.data["file"]
        workflow = Workflow.objects.get(id=kwargs["workflow_id"])
        if not workflow:
            raise KeyError(
                "No workflow found for id %s not found", kwargs["workflow_id"]
            )
        content = decode_utf8(file_obj)  # .read()
        try:
            process_csv(content, workflow=workflow)
        except Exception as exception:
            return Response(
                {"status_code": 400, "errors": [{"message": str(exception)}]},
                status=400,
            )
        return Response(status=200)


class ListTaskView(ListAPIView):
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
            Q(workflow__in=workflows) & Q(workflow=self.kwargs["workflow_id"])
        )

    def list(self, request, *args, **kwargs):
        workflow = Workflow.objects.get(id=kwargs["workflow_id"])
        obj = get_list_or_404(self.get_queryset(), workflow=workflow)
        serializer = self.serializer_class(obj, many=True)
        return Response(serializer.data)


class RUDTaskView(RetrieveUpdateAPIView):
    """
    Retrieve and Update for now, will add delete here later
    """

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
            Q(workflow__in=workflows) & Q(workflow=self.kwargs["workflow_id"])
        )

    def get_object(self):
        workflow = Workflow.objects.get(id=self.kwargs["workflow_id"])
        queryset = self.get_queryset()
        obj = get_object_or_404(queryset, id=self.kwargs["task_id"], workflow=workflow)
        return obj

    def retrieve(self, *args, **kwargs):
        workflow = Workflow.objects.get(id=self.kwargs["workflow_id"])
        queryset = self.get_queryset()
        obj = get_object_or_404(queryset, id=self.kwargs["task_id"], workflow=workflow)
        task = self.serializer_class(obj).data
        return Response(task)

    def perform_update(self, serializer, *args, **kwargs):
        serializer.save(owner=self.request.user)


class NextTaskView(APIView):
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
            Q(workflow__in=workflows) & Q(workflow=self.kwargs["workflow_id"])
        )

    def get(self, request, *args, **kwargs):
        workflow = Workflow.objects.get(id=kwargs["workflow_id"])
        queryset = self.get_queryset()

        # 1 get assigned to self
        obj = (
            queryset.filter(status="assigned").filter(assigned_to=request.user).first()
        )
        if obj:
            task = self.serializer_class(obj).data
            return Response(task)

        # 2 get assigned to someone else and expired
        with transaction.atomic():
            obj = queryset.select_for_update().filter(status="assigned").first()
            if obj and timezone.now() - obj.assigned_at > timezone.timedelta(
                minutes=settings.TASK_EXPIRATION_MIN
            ):
                obj.assigned_to = request.user
                obj.assigned_at = timezone.now()
                obj.save()
                task = self.serializer_class(obj).data
                return Response(task)

        # 3 get first pending
        with transaction.atomic():
            obj = queryset.select_for_update().filter(status="pending").first()
            if not obj:
                return Response({}, status=204)
            obj.status = "assigned"
            obj.assigned_to = request.user
            obj.assigned_at = timezone.now()
            obj.save()
            workflow.n_tasks = F("n_tasks") - 1
            workflow.save()
            task = self.serializer_class(obj).data
            return Response(task)


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

    def post(self, request, *args, **kwargs):
        workflow = Workflow.objects.get(id=kwargs["workflow_id"])
        if not workflow:
            return Response(
                {
                    "status_code": 404,
                    "errors": [
                        {
                            "message": "Workflow with id {} was not found".format(
                                kwargs["workflow_id"]
                            )
                        }
                    ],
                },
                status=404,
            )
        request.data["outputs"] = workflow.outputs
        if "inputs" not in request.data or not request.data["inputs"]:
            return Response(
                {"status_code": 400, "errors": [{"message": "No inputs"}]}, status=400,
            )
        for task_input in request.data["inputs"]:
            try:
                workflow_input = next(
                    {"name": item["name"], "type": item["type"]}
                    for item in workflow.inputs
                    if item["id"] == task_input["id"]
                )
            except StopIteration:
                return Response(
                    {
                        "status_code": 400,
                        "errors": [
                            {
                                "message": "Cannot find input with input id: {}".format(
                                    task_input["id"]
                                )
                            }
                        ],
                    },
                    status=400,
                )
            task_input.update(workflow_input)
        workflow.n_tasks = F("n_tasks") + 1
        workflow.save()
        return self.create(request, *args, **kwargs)


class TaskPagination(LimitOffsetPagination):
    """
    Extended pagination class for Tasks
    """

    default_limit = 100
    max_limit = 1000

    def get_paginated_response(self, data):
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "count": self.count,
                "tasks": data,
            }
        )


class GetCompletedTaskView(ListAPIView):
    """
    External API View for getting all the Tasks
    """

    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = TaskSerializer
    pagination_class = TaskPagination

    def get_queryset(self):
        user = self.request.user
        organizations = Organization.objects.filter(user=user).all()
        workflows = Workflow.objects.filter(
            Q(organization__in=organizations)
            & Q(organization__pk=self.kwargs["org_id"])
        )
        return Task.objects.filter(
            Q(workflow__in=workflows)
            & Q(workflow=self.kwargs["workflow_id"])
            & Q(status="completed")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        obj = get_list_or_404(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(obj, many=True)
        return Response(serializer.data)
