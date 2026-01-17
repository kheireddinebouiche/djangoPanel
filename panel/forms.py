from django import forms
from .models import Project

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'domain', 'repo_url', 'branch', 'port', 'python_version', 'env_vars']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'My Awesome App'}),
            'domain': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'app.example.com'}),
            'repo_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://github.com/user/repo'}),
            'branch': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'main'}),
            'port': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '8000'}),
            'python_version': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '3.11'}),
            'env_vars': forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'placeholder': 'DEBUG=True\nSECRET_KEY=...'}),
        }
