# Setting up to run scripts using the openai API with Python.

The script will be run in a virtual environment.

The first step is to create a virtual environment. You can name the virtual environment `venv` or you can give it the same name as your project:

On a Mac:
`python3 -m venv chefboost-env`

or: `python3 -m venv venv`

On Windows:
`python -m venv chefboost-env`

or: `python -m venv venv`

<br>
After creating the virtual environment, you need to activate it:

On a Mac:
`source chefboost-env/bin/activate`

On Windows:
`source chefboost-env/Scripts/activate`

<br>
Once the virtual environment is activated, the beginning of your terminal prompt should display (chefboost-env).

<br>
Install the necessary modules by running:

On a Mac:
`pip3 install -r requirements.txt`

On Windows:
`pip install -r requirements.txt`

<br>
To run your code, in the command line run:

## Flask:

Without a debugger:
`flask run`

With a debugger:
`flask run --debug`

## The app.py file:

On a Mac:
`python3 app.py`

On Windows:
`python app.py`

## Example of running a file using a CLI built with argparse: books_storage_and_retrieval.py file:

On a Mac:
`python3 books_storage_and_retrieval.py -lb True`

On Windows:
`python books_storage_and_retrieval.py  -lb True`

<br>
The app will run at: http://127.0.0.1:5000/

<br>
To stop the run, click control + C.
Then hard refresh the page. When making changes to your Python, HTML, or JavaScript code (and not using debugger) you'll need to stop the run after each change.

<br>
When finished, quit the run by clicking control + C and close the virtual environment by running:

`deactivate`

## Deploying to Google App Engine

This application includes deployment scripts and configuration for Google App Engine. Here's how to deploy:

### Prerequisites

1. Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
2. Create a Google Cloud Platform account and project
3. Have a `.env` file with the following environment variables:
   - `OPENAI_API_KEY`
   - `SUPABASE_HTTPS_URL`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SECRET_KEY` (optional - will be auto-generated if not provided)

### Deployment Steps

1. **Run the deployment script**:

   ```bash
   python deploy.py
   ```

   This script will:

   - Check for required environment variables
   - Create necessary deployment files (secret.yaml, .gcloudignore)
   - Ensure gunicorn is added to requirements.txt
   - Set up your Google Cloud project
   - Deploy the application to Google App Engine

2. **Follow the interactive prompts**:

   - Confirm deployment when prompted
   - Enter your Google Cloud Project ID
   - Select an App Engine region (default is us-central)

3. **Wait for deployment to complete**:
   - The deployment process may take several minutes
   - Upon completion, the script will display your application URL

### Understanding the Deployment Files

- **deploy.py**: Automates the deployment process, creates necessary config files and handles GCP setup
- **app.yaml**: Defines the runtime configuration for Google App Engine:
  - Python 3.12 runtime
  - F2 instance class
  - Gunicorn web server
  - Scaling settings
  - Static file handlers
- **secret.yaml**: Created automatically by deploy.py, contains environment variables
- **.gcloudignore**: Specifies which files should not be uploaded to Google App Engine

### Monitoring and Troubleshooting

After deployment, you can:

- View logs: `gcloud app logs tail`
- Check application status: `gcloud app describe`
- Open the application: `gcloud app browse`
