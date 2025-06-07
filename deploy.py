#!/usr/bin/env python3
"""
Google App Engine deployment script for ChefBoost application
"""

import os
import sys
import subprocess
import secrets
from pathlib import Path
from dotenv import load_dotenv

# ANSI color codes for terminal output
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m'  # No Color

def colored_print(color, message):
    """Print colored message to terminal"""
    print(f"{color}{message}{NC}")

def run_command(command, check=True, capture_output=False):
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=check,
            text=True,
            capture_output=capture_output
        )
        return result
    except subprocess.CalledProcessError as e:
        colored_print(RED, f"Command failed: {command}")
        colored_print(RED, f"Error: {e}")
        if check:
            sys.exit(1)
        return e

def check_env_variables(required_vars):
    """Check if required environment variables are set"""
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        colored_print(RED, "Error: The following required variables are not set in .env file:")
        for var in missing_vars:
            print(f"  - {var}")
        sys.exit(1)

def create_secret_yaml():
    """Create secret.yaml with environment variables"""
    colored_print(YELLOW, "Creating secret.yaml with environment variables...")
    
    env_vars = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "SUPABASE_HTTPS_URL": os.environ.get("SUPABASE_HTTPS_URL", ""),
        "SUPABASE_URL": os.environ.get("SUPABASE_URL", ""),
        "SUPABASE_KEY": os.environ.get("SUPABASE_KEY", ""),
        "LANGCHAIN_TRACING_V2": os.environ.get("LANGCHAIN_TRACING_V2", ""),
        "LANGCHAIN_ENDPOINT": os.environ.get("LANGCHAIN_ENDPOINT", ""),
        "LANGCHAIN_API_KEY": os.environ.get("LANGCHAIN_API_KEY", ""),
        "LANGCHAIN_PROJECT": os.environ.get("LANGCHAIN_PROJECT", ""),
        "SECRET_KEY": os.environ.get("SECRET_KEY", "")
    }
    
    with open("secret.yaml", "w") as f:
        f.write("env_variables:\n")
        for key, value in env_vars.items():
            f.write(f"  {key}: \"{value}\"\n")

def create_gcloudignore():
    """Create .gcloudignore file to avoid uploading unnecessary files"""
    colored_print(YELLOW, "Creating .gcloudignore file...")
    
    ignore_patterns = [
        ".git", ".gitignore", ".env", ".env.sample",
        "__pycache__/", "*.py[cod]", "*$py.class", "*.so",
        ".Python", "env/", "venv/", "chefboost-env/", "ENV/", "build/",
        "develop-eggs/", "dist/", "downloads/", "eggs/",
        ".eggs/", "lib/", "lib64/", "parts/", "sdist/", "var/",
        "*.egg-info/", ".installed.cfg", "*.egg", "*.db",
        ".vscode/", "node_modules/", ".pytest_cache/",
        "gutenberg/cache/", "gutenberg/texts/", "texts/",
        "tests/", "supabase/", "lessons/", "design/",
        "*.bz2", "*.md"
    ]
    
    with open(".gcloudignore", "w") as f:
        for pattern in ignore_patterns:
            f.write(f"{pattern}\n")

def check_gunicorn_in_requirements():
    """Ensure gunicorn is in requirements.txt"""
    with open("requirements.txt", "r") as f:
        content = f.read()
    
    if "gunicorn" not in content:
        colored_print(YELLOW, "Adding gunicorn to requirements.txt...")
        with open("requirements.txt", "a") as f:
            f.write("\ngunicorn==21.2.0\n")

def deploy_to_app_engine():
    """Main deployment function"""
    colored_print(GREEN, "ChefBoost App GAE Deployment")
    print("This script will deploy the ChefBoost application to Google App Engine")
    
    # Check if .env file exists and load it
    env_file = Path(".env")
    if not env_file.exists():
        colored_print(RED, "Error: .env file not found")
        print("Please create a .env file with the required environment variables")
        sys.exit(1)
    
    load_dotenv(override=True)
    
    # Check for required variables
    required_vars = [
        "OPENAI_API_KEY",
        "SUPABASE_HTTPS_URL",
        "SUPABASE_URL",
        "SUPABASE_KEY"
    ]
    check_env_variables(required_vars)
    
    # Generate a random SECRET_KEY if not provided
    if not os.environ.get("SECRET_KEY"):
        os.environ["SECRET_KEY"] = secrets.token_hex(24)
        colored_print(YELLOW, "Generated random SECRET_KEY")
    
    colored_print(YELLOW, "Preparing deployment files...")
    
    # Create config files
    create_secret_yaml()
    create_gcloudignore()
    check_gunicorn_in_requirements()
    
    # Confirm deployment
    colored_print(YELLOW, "Ready to deploy to Google App Engine. This may take several minutes.")
    response = input("Continue with deployment? (y/n) ")
    if not response.lower().startswith('y'):
        colored_print(RED, "Deployment cancelled")
        sys.exit(0)
    
    # Get project ID and set in gcloud config
    project_id = input("Enter your Google Cloud Project ID: ")
    if not project_id:
        colored_print(RED, "Error: Project ID cannot be empty")
        sys.exit(1)
    
    colored_print(YELLOW, f"Setting GCP project to: {project_id}")
    run_command(f"gcloud config set project {project_id}")
    
    # Enable required services
    colored_print(YELLOW, "Enabling required Google Cloud services...")
    run_command("gcloud services enable appengine.googleapis.com cloudbuild.googleapis.com")
    
    # Set the App Engine region
    region = input("Enter App Engine region (default: us-central): ") or "us-central"
    
    # Check if app has been created
    result = run_command("gcloud app describe", check=False, capture_output=True)
    if result.returncode != 0:
        colored_print(YELLOW, f"Creating App Engine application in region {region}...")
        run_command(f"gcloud app create --region={region}")
    
    # Deploy the application
    colored_print(YELLOW, "Deploying application to Google App Engine...")
    run_command("gcloud app deploy app.yaml --quiet")
    
    # Display deployment information
    colored_print(GREEN, "Deployment completed!")
    result = run_command("gcloud app describe --format='value(defaultHostname)'", capture_output=True)
    hostname = result.stdout.strip()
    colored_print(GREEN, f"Your application URL: https://{hostname}")
    
    # Cleanup
    colored_print(YELLOW, "Cleaning up temporary deployment files...")
    
    colored_print(GREEN, "Deployment process completed successfully!")
    print("Visit your application and check the logs for any issues.")
    colored_print(YELLOW, "To view logs: gcloud app logs tail")

if __name__ == "__main__":
    deploy_to_app_engine()