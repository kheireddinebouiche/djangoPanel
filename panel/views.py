from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Project, Deployment
from .forms import ProjectForm
from .services import DeployService
import threading
import os
import sys

def stop_server(request):
    """Stops the Django development server."""
    if request.user.is_superuser or request.user.is_staff: # basic protection
        # We start a thread to kill after response is sent, hopefully
        def kill():
            import time
            time.sleep(1)
            os._exit(0)
            
        threading.Thread(target=kill).start()
        return render(request, 'panel/server_stopped.html')
    else:
        messages.error(request, "Permission denied.")
        return redirect('dashboard')


def dashboard(request):
    projects = Project.objects.all().order_by('-created_at')
    return render(request, 'panel/dashboard.html', {'projects': projects})

def create_project(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            messages.success(request, f"Project '{project.name}' created! Deployment started...")
            
            # Start initial deployment
            deployment = Deployment.objects.create(project=project, status='pending')
            thread = threading.Thread(target=DeployService.deploy, args=(project, deployment))
            thread.start()
            
            return redirect('project_detail', project_id=project.id)
    else:
        form = ProjectForm()
    return render(request, 'panel/create_project.html', {'form': form})

def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    deployments = project.deployments.all().order_by('-created_at')[:5]
    return render(request, 'panel/project_detail.html', {'project': project, 'deployments': deployments})

def deploy_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    deployment = Deployment.objects.create(project=project, status='pending')
    
    thread = threading.Thread(target=DeployService.deploy, args=(project, deployment))
    thread.start()
    
    messages.success(request, f"Manual deployment triggered for {project.name}.")
    return redirect('project_detail', project_id=project.id)

def delete_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        success, msg = DeployService.remove_project(project)
        if success:
            project.delete()
            messages.success(request, f"Project '{project.name}' deleted successfully.")
            return redirect('dashboard')
        else:
            messages.error(request, f"Error deleting project: {msg}")
            
    return redirect('project_detail', project_id=project.id)

def project_files(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    subpath = request.GET.get('path', '')
    
    # Imports inside view to avoid circular dep if any, though here it's fine
    from .services import FileService
    
    try:
        files, error = FileService.list_files(project, subpath)
        if error:
            messages.error(request, error)
            files = []
    except ValueError:
        messages.error(request, "Invalid path.")
        files = []
        
    # Breadcrumbs
    breadcrumbs = []
    parts = subpath.strip('/').split('/')
    current = ''
    if subpath:
        for part in parts:
            if part:
                current = f"{current}/{part}" if current else part
                breadcrumbs.append({'name': part, 'path': current})

    return render(request, 'panel/file_browser.html', {
        'project': project,
        'files': files,
        'current_path': subpath,
        'breadcrumbs': breadcrumbs
    })

    return render(request, 'panel/file_browser.html', {
        'project': project,
        'files': files,
        'current_path': subpath,
        'breadcrumbs': breadcrumbs
    })

def update_panel(request):
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
        
    if request.method == 'POST':
        def run_update():
            from .services import PanelUpdateService
            PanelUpdateService.update()
            
        threading.Thread(target=run_update).start()
        messages.success(request, "Update started! The panel will restart in a few seconds.")
        return redirect('dashboard')
        
    return redirect('dashboard')

from django.http import JsonResponse
import json

def project_terminal(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            command = data.get('command')
            if not command:
                 return JsonResponse({'error': 'No command provided'}, status=400)
                 
            from .services import ConsoleService
            result = ConsoleService.run_command(project, command)
            return JsonResponse(result)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return render(request, 'panel/terminal.html', {'project': project})

def project_file_edit(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    subpath = request.GET.get('path', '')
    
    from .services import FileService
    
    if request.method == 'POST':
        content = request.POST.get('content')
        success, error = FileService.save_file(project, subpath, content)
        if success:
            messages.success(request, "File saved successfully.")
        else:
            messages.error(request, f"Error saving file: {error}")
            
    content, error = FileService.read_file(project, subpath)
    if error:
        messages.error(request, error)
        return redirect('project_files', project_id=project.id)
        
    return render(request, 'panel/file_editor.html', {
        'project': project,
        'path': subpath,
        'content': content,
        'filename': subpath.split('/')[-1]
    })
