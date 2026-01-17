from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('create/', views.create_project, name='create_project'),
    path('project/<int:project_id>/', views.project_detail, name='project_detail'),
    path('project/<int:project_id>/deploy/', views.deploy_project, name='deploy_project'),
    path('project/<int:project_id>/delete/', views.delete_project, name='delete_project'),
    path('project/<int:project_id>/files/', views.project_files, name='project_files'),
    path('project/<int:project_id>/terminal/', views.project_terminal, name='project_terminal'),
    path('update/', views.update_panel, name='update_panel'),
    path('stop-server/', views.stop_server, name='stop_server'),
]
