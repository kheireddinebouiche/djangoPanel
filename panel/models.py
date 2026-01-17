from django.db import models
from django.utils.translation import gettext_lazy as _

class Project(models.Model):
    name = models.CharField(max_length=100)
    domain = models.CharField(max_length=200, help_text="e.g. app.example.com")
    repo_url = models.CharField(max_length=300, help_text="https://github.com/user/repo")
    branch = models.CharField(max_length=100, default='main')
    port = models.IntegerField(unique=True, help_text="Internal Gunicorn port (e.g. 8000)")
    python_version = models.CharField(max_length=10, default='3.11')
    
    # Environment variables (stored as simple text for MVP, one per line)
    env_vars = models.TextField(blank=True, help_text="KEY=VALUE (one per line)")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Deployment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='deployments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    logs = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.name} - {self.status} - {self.created_at}"
