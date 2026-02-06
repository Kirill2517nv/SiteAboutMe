import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Configure queue for code execution tasks
app.conf.task_routes = {
    'quizzes.tasks.check_code_task': {'queue': 'code_execution'},
}

# Default queue for other tasks
app.conf.task_default_queue = 'default'
