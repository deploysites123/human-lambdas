from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone
from user_handler.permissions import IsOrgAdmin
from user_handler.models import User, Organization, Invitation, Notification
from django.shortcuts import get_object_or_404
from workflow_handler.models import WorkflowNotification
from hl_rest_api.utils import is_invalid_email, generate_unique_token

from .apps import UserHandlerConfig


class SendInviteView(APIView):
    permission_classes = (IsAuthenticated, IsOrgAdmin)

    def get_queryset(self):
        return Invitation.objects.filter(
            organization__pk=self.kwargs["org_id"]
        ).distinct()

    def get(self, request, *args, **kwargs):
        invited_users = [
            {"email": invitation.email, "pending": True, "is_admin": invitation.admin}
            for invitation in self.get_queryset()
        ]
        return Response(
            {"status_code": 200, "invited_users": invited_users}, status=200
        )

    def post(self, request, *args, **kwargs):
        email_set = set("".join(request.data["emails"].split()).split(","))
        invalid_email_list, already_added_email_list = [], []
        organization = Organization.objects.get(pk=kwargs["org_id"])
        template_data = []
        emails = []
        for email in email_set:
            if is_invalid_email(email):
                invalid_email_list.append(email)
                continue

            if Organization.objects.filter(user__email=email).exists():
                already_added_email_list.append(email)
                continue

            token = generate_unique_token(email, kwargs["org_id"])
            Invitation(
                email=email,
                organization=organization,
                invited_by=request.user,
                token=token,
                expires_at=timezone.now()
                + timezone.timedelta(days=settings.INVITATION_EXPIRATION_WINDOW_DAYS),
            ).save()

            if not User.objects.filter(email=email).exists():
                invite_link = "{0}invite/{1}".format(settings.FRONT_END_BASE_URL, token)
            else:
                invite_link = "{0}invite/success/{1}".format(
                    settings.FRONT_END_BASE_URL, token
                )

            template_data.append(
                {
                    "org_name": organization.name,
                    "inviter_name": request.user.name,
                    "url": invite_link,
                }
            )
            emails.append(email)

        UserHandlerConfig.emailclient.send_email(
            to_email=emails,
            template_id=settings.INVITATION_TEMPLATE,
            template_data=template_data,
            group_id=int(settings.ACCOUNT_ASM_GROUPID),
        )

        # sending responses
        if len(invalid_email_list) == 0 and len(already_added_email_list) == 0:
            return Response(
                {"status_code": 200, "message": "all emails were successfully added!"},
                status=200,
            )
        response_text = ""
        for email in invalid_email_list:
            response_text += "{0} is an invalid email. ".format(email)
        for email in already_added_email_list:
            response_text += "{0} is already a part of the organization. ".format(email)
        return Response(
            {"status_code": 400, "errors": [{"message": response_text}]}, status=400
        )

    def patch(self, request, *args, **kwargs):
        invites = self.get_queryset().filter(email=self.request.data["email"])
        if not invites.exists():
            return Response(
                {
                    "status_code": 400,
                    "errors": [
                        {"message": "there are no invitations to this user to update"}
                    ],
                },
                status=400,
            )
        for invite in invites:
            invite.admin = True if self.request.data["admin"] else False
            invite.save()
        if self.request.data["admin"]:
            response_text = "this invitation has now been set to admin status"
        else:
            response_text = "this invitation has now been set to worker status"
        return Response({"status_code": 200, "message": response_text}, status=200)

    def delete(self, request, *args, **kwargs):
        invites = self.get_queryset().filter(email=self.request.data["email"])
        if not invites.exists():
            return Response(
                {
                    "status_code": 400,
                    "errors": [
                        {"message": "there are no invitations to this user to delete"}
                    ],
                },
                status=400,
            )
        for invite in invites:
            invite.delete()
        response_text = "this invite has now been deleted"
        return Response({"status_code": 200, "message": response_text}, status=200)


class InvitationView(APIView):
    permission_classes = (AllowAny,)

    def get_queryset(self):
        return Invitation.objects.filter(token=self.kwargs["invite_token"])

    def get(self, request, *args, **kwargs):
        invite = get_object_or_404(self.get_queryset())
        invitation_email, invitation_org = (
            invite.email,
            invite.organization.name,
        )
        return Response(
            {
                "status_code": 200,
                "invitation_email": invitation_email,
                "invitation_org": invitation_org,
            },
            status=200,
        )

    def post(self, request, *args, **kwargs):
        invite = get_object_or_404(self.get_queryset())
        if invite.expires_at < timezone.now():
            return Response(
                {
                    "status_code": 400,
                    "errors": [{"message": "this token has expired!"}],
                },
                status=400,
            )

        invitation_org = invite.organization
        if invitation_org.user.filter(email=invite.email).exists():
            return Response(
                {
                    "status_code": 400,
                    "errors": [
                        {"message": "this organization has already been joined"}
                    ],
                },
                status=400,
            )
        user = User.objects.filter(email=invite.email).first()
        if not user:
            notification = Notification()
            notification.save()
            user = User(
                email=invite.email,
                name=request.data["name"],
                current_organization_id=invitation_org.id,
                notifications=notification,
            )
            user.set_password(request.data["password"])
            user.save()
            response_data = {
                "data": {
                    "status_code": 201,
                    "message": "Your account has been created!",
                    "email": invite.email,
                },
                "status": 201,
            }
        else:
            response_data = {
                "data": {
                    "status_code": 200,
                    "message": "Success!",
                    "email": invite.email,
                },
                "status": 200,
            }

        for workflow in invitation_org.workflow_set.all():
            WorkflowNotification(workflow=workflow, notification=notification).save()

        if invite.admin:
            invitation_org.add_admin(user)
        else:
            invitation_org.user.add(user)

        Invitation.objects.filter(
            organization__pk=invitation_org.id, email=invite.email
        ).all().delete()
        return Response(**response_data)
