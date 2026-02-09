import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class QuizConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time quiz code submission updates.
    Each user joins a group: user_{user_id}_quiz_{quiz_id}
    """

    async def connect(self):
        self.user = self.scope['user']

        # Reject anonymous users
        if self.user.is_anonymous:
            await self.close()
            return

        self.quiz_id = self.scope['url_route']['kwargs']['quiz_id']
        self.group_name = f"user_{self.user.id}_quiz_{self.quiz_id}"

        # Join user's quiz group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

        # Send current pending/running submissions on connect
        await self.send_active_submissions()

    async def disconnect(self, close_code):
        # Leave group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages (e.g., status requests).
        """
        try:
            data = json.loads(text_data)
            action = data.get('action')

            if action == 'get_status':
                await self.send_active_submissions()
        except json.JSONDecodeError:
            pass

    async def submission_update(self, event):
        """
        Handle submission update messages from Celery task.
        """
        await self.send(text_data=json.dumps({
            'type': 'submission_update',
            'submission_id': event['submission_id'],
            'question_id': event['question_id'],
            'status': event['status'],
            'is_correct': event['is_correct'],
            'error_log': event['error_log'],
            'event_type': event['event_type'],
        }))

    async def help_comment_update(self, event):
        """
        Handle help comment messages from teacher replies.
        Forwards to client so HelpRequestManager can display inline.
        """
        await self.send(text_data=json.dumps({
            'type': 'help_comment',
            'question_id': event['question_id'],
            'comment': event['comment'],
            'status': event.get('status'),
            'resolved': event.get('resolved', False),
        }))

    @database_sync_to_async
    def get_active_submissions(self):
        """
        Get all pending/running submissions for this user and quiz.
        """
        from .models import CodeSubmission

        submissions = CodeSubmission.objects.filter(
            user=self.user,
            quiz_id=self.quiz_id,
            status__in=['pending', 'running']
        ).values('id', 'question_id', 'status')

        return list(submissions)

    async def send_active_submissions(self):
        """
        Send list of active submissions to the client.
        """
        submissions = await self.get_active_submissions()
        await self.send(text_data=json.dumps({
            'type': 'active_submissions',
            'submissions': submissions,
        }))


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Global WebSocket consumer for navbar badge notifications.
    Groups: notifications_{user_id} (personal) + notifications_teachers (for superusers)
    """

    async def connect(self):
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        self.personal_group = f"notifications_{self.user.id}"
        await self.channel_layer.group_add(
            self.personal_group,
            self.channel_name
        )

        # Superusers also join the teachers group
        if self.user.is_superuser:
            await self.channel_layer.group_add(
                'notifications_teachers',
                self.channel_name
            )

        await self.accept()

        # Send current unread count on connect
        count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'unread_count_update',
            'unread_count': count,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'personal_group'):
            await self.channel_layer.group_discard(
                self.personal_group,
                self.channel_name
            )
        if hasattr(self, 'user') and self.user.is_superuser:
            await self.channel_layer.group_discard(
                'notifications_teachers',
                self.channel_name
            )

    async def help_notification(self, event):
        """
        New help request or reply — update badge count.
        """
        count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'help_notification',
            'help_request_id': event.get('help_request_id'),
            'question_id': event.get('question_id'),
            'quiz_id': event.get('quiz_id'),
            'student_name': event.get('student_name'),
            'unread_count': count,
        }))

    @database_sync_to_async
    def get_unread_count(self):
        from .models import HelpRequest
        if self.user.is_superuser:
            return HelpRequest.objects.filter(
                has_unread_for_teacher=True
            ).exclude(status='resolved').count()
        else:
            return HelpRequest.objects.filter(
                student=self.user,
                has_unread_for_student=True
            ).count()
