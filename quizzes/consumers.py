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
