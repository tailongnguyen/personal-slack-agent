#!/bin/bash
# Run the main FastAPI app for the personal-slack-agent

# Optional: activate your virtual environment
# source venv/bin/activate

# Run the FastAPI app using uvicorn
uvicorn main_ast:fastapi_app --host 0.0.0.0 --port 16110 --reload
