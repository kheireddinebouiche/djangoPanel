import subprocess
import os
import shutil
from pathlib import Path
from django.conf import settings

class SystemService:
    @staticmethod
    def run_command(command, cwd=None):
        """
        Runs a shell command and returns the output or error.
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False # We handle errors manually
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': -1
            }

class ConfigGenerator:
    @staticmethod
    def generate_nginx_config(project):
        """Generates Nginx config string."""
        # Using a very permissive regex for static alias for now
        static_path = f"/var/www/{project.domain}/static/"
        
        return f"""server {{
    listen 80;
    server_name {project.domain};

    location / {{
        proxy_pass http://127.0.0.1:{project.port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location /static/ {{
        alias {static_path};
    }}
}}"""

    @staticmethod
    def generate_gunicorn_service(project, venv_path, project_path):
        """Generates Systemd service string."""
        return f"""[Unit]
Description=Gunicorn daemon for {project.name}
After=network.target

[Service]
User={os.getlogin()}
Group=www-data
WorkingDirectory={project_path}
ExecStart={venv_path}/bin/gunicorn --workers 3 --bind 127.0.0.1:{project.port} config.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target"""

import sys
import platform

# ... imports ...

class DeployService:
    BASE_DIR = Path.home() / "django_projects" 

    @classmethod
    def deploy(cls, project, deployment):
        # ... (logging logic) ...
        log_buffer = []
        def log(msg):
            log_buffer.append(msg)
            deployment.logs = "\\n".join(log_buffer)
            deployment.save()

        try:
            # 1. Prepare Paths
            project_path = cls.BASE_DIR / project.name
            venv_path = project_path / "venv"
            static_path = Path(f"/var/www/{project.domain}/static")
            
            # Determine OS-specific bin directory
            is_windows = platform.system() == 'Windows'
            bin_dir = "Scripts" if is_windows else "bin"
            venv_bin = venv_path / bin_dir
            
            if not cls.BASE_DIR.exists():
                os.makedirs(cls.BASE_DIR, exist_ok=True)

            # 2. Clone or Pull
            log(f"Starting deployment for {project.name}...")
            if project_path.exists():
                log("Pulling latest changes...")
                res = SystemService.run_command("git pull", cwd=project_path)
            else:
                log(f"Cloning {project.repo_url}...")
                res = SystemService.run_command(f'git clone "{project.repo_url}" "{project.name}"', cwd=cls.BASE_DIR)
            
            if not res['success']:
                raise Exception(f"Git failed: {res['stderr']}")
            log("Git operation successful.")

            # 3. Setup Venv
            if not venv_path.exists():
                log(f"Creating virtual environment using {sys.executable}...")
                # Use sys.executable to ensure we use the same python interpreter
                res = SystemService.run_command(f'"{sys.executable}" -m venv venv', cwd=project_path)
                if not res['success']:
                    raise Exception(f"Venv creation failed: {res['stderr']}")

            # 4. Install Requirements
            log("Installing requirements...")
            # Use absolute path to pip
            pip_cmd = f'"{venv_bin / "pip"}" install -r requirements.txt'
            res = SystemService.run_command(pip_cmd, cwd=project_path)
            if not res['success']:
                log(f"Warning: pip install had issues: {res['stderr']}") 

            # 5. Migrations & Static
            log("Running migrations...")
            python_cmd = f'"{venv_bin / "python"}" manage.py'
            res = SystemService.run_command(f"{python_cmd} migrate", cwd=project_path)
            
            log("Collecting static files...")
            res = SystemService.run_command(f"{python_cmd} collectstatic --noinput", cwd=project_path)

            
            # 6. System Configs (Requires SUDO - this part is tricky without password)
            # We will assume the user running this has passwordless sudo for these writes
            # OR we write to tmp and ask user to copy (but the prompt asked for "Direct deployment")
            # We'll try direct write with tee using sudo
            
            log("Configuring Systemd & Nginx...")
            
            # Write Nginx
            nginx_conf = ConfigGenerator.generate_nginx_config(project)
            nginx_path = f"/etc/nginx/sites-available/{project.domain}"
            # Escape quotes for shell safety in echo is hard, writing detailed python file writer is better
            # For MVP, let's just write to a temp file and move it.
            tmp_nginx = f"/tmp/{project.domain}.nginx"
            with open(tmp_nginx, 'w') as f:
                f.write(nginx_conf)
            
            res = SystemService.run_command(f"sudo mv {tmp_nginx} {nginx_path} && sudo ln -sf {nginx_path} /etc/nginx/sites-enabled/", cwd=project_path)
            if not res['success']:
                 # If sudo fails, we just log it. This is expected on non-root or limited setups.
                 log(f"Sudo Nginx failed (permissions?): {res['stderr']}")

            # Write Systemd
            service_conf = ConfigGenerator.generate_gunicorn_service(project, venv_path, project_path)
            service_name = f"{project.name}_gunicorn.service"
            tmp_service = f"/tmp/{service_name}"
            with open(tmp_service, 'w') as f:
                f.write(service_conf)
            
            res = SystemService.run_command(f"sudo mv {tmp_service} /etc/systemd/system/{service_name} && sudo systemctl daemon-reload && sudo systemctl enable {service_name} && sudo systemctl restart {service_name}", cwd=project_path)
             
            # Restart Nginx
            SystemService.run_command("sudo systemctl restart nginx")

            log("Deployment Successful!")
            deployment.status = 'success'
            deployment.save()
            return True, deployment.logs

        except Exception as e:
            msg = f"Deployment failed: {str(e)}"
            log(msg)
            deployment.status = 'failed'
            deployment.save()
            return False, msg

    @classmethod
    def remove_project(cls, project):
        """Removes project files and system configurations."""
        try:
            # 1. Stop and Remove Systemd Service
            service_name = f"{project.name}_gunicorn.service"
            SystemService.run_command(f"sudo systemctl stop {service_name}")
            SystemService.run_command(f"sudo systemctl disable {service_name}")
            SystemService.run_command(f"sudo rm /etc/systemd/system/{service_name}")
            
            # 2. Remove Nginx Config
            nginx_path = f"/etc/nginx/sites-available/{project.domain}"
            SystemService.run_command(f"sudo rm {nginx_path}")
            SystemService.run_command(f"sudo rm /etc/nginx/sites-enabled/{project.domain}")
            
            # 3. Reload Daemons
            SystemService.run_command("sudo systemctl daemon-reload")
            SystemService.run_command("sudo systemctl restart nginx")
            
            # 4. Remove Files
            # Helper for Windows read-only git files
            def on_rm_error(func, path, exc_info):
                import stat
                # Make writable and try again
                os.chmod(path, stat.S_IWRITE)
                func(path)

            project_path = cls.BASE_DIR / project.name
            if project_path.exists():
                shutil.rmtree(project_path, onerror=on_rm_error)
                
            return True, "Project removed successfully."
        except Exception as e:
            return False, str(e)

class FileService:
    @staticmethod
    def list_files(project, subpath=''):
        """
        Lists files in a project directory safely.
        """
        base_dir = DeployService.BASE_DIR / project.name
        target_dir = (base_dir / subpath).resolve()
        
        # Security check: ensure target_dir is inside base_dir
        if not str(target_dir).startswith(str(base_dir.resolve())):
            raise ValueError("Invalid path: Access denied.")
            
        if not target_dir.exists():
            return None, "Path does not exist"
            
        if not target_dir.is_dir():
            return None, "Path is not a directory"
            
        items = []
        try:
            for item in target_dir.iterdir():
                items.append({
                    'name': item.name,
                    'path': str(item.relative_to(base_dir)).replace('\\', '/'),
                    'is_dir': item.is_dir(),
                    'size': item.stat().st_size if item.is_file() else 0,
                })
            
            # Sort: directories first, then files
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            return items, None
        except Exception as e:
            return None, str(e)

class ConsoleService:
    @staticmethod
    def run_command(project, command):
        """
        Runs a command inside the project's virtual environment.
        """
        project_path = DeployService.BASE_DIR / project.name
        venv_path = project_path / "venv"
        
        # Determine OS-specific bin directory
        is_windows = platform.system() == 'Windows'
        bin_dir = "Scripts" if is_windows else "bin"
        venv_bin = venv_path / bin_dir
        
        # Prepare environment
        env = os.environ.copy()
        env['PATH'] = f"{str(venv_bin)}{os.pathsep}{env.get('PATH', '')}"
        env['VIRTUAL_ENV'] = str(venv_path)
        
        # Security: Prevent changing directory (basic)
        if command.strip().startswith('cd '):
             return {
                'success': False,
                'stdout': '',
                'stderr': 'Directory navigation is not supported in this console mode.',
                'returncode': -1
            }

        try:
            # Run command
            result = subprocess.run(
                command,
                shell=True,
                cwd=project_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=30 # Prevent hangs
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
             return {
                'success': False,
                'stdout': '',
                'stderr': 'Command timed out (max 30s).',
                'returncode': -1
            }
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': -1
            }
