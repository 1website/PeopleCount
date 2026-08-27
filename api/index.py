import sys
import os

# Add root directory to sys.path so that 'app' can be imported by Vercel serverless function
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.main import app

# Expose app for Vercel
__all__ = ["app"]
