#!/usr/bin/env python3
"""
Run script for the Calendar AI application.
This ensures the backend directory is in the Python path.
"""
import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(project_root, "backend"))

from app import app

if __name__ == "__main__":
    print("✅ Starting Flask app...")
    app.run(debug=True, port=8080) 