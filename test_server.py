"""
test_server.py - Quick test to verify gunicorn can import the server object

Run this before deploying to ensure the app structure is correct:
    python test_server.py

Expected output:
    ✓ Successfully imported app module
    ✓ Found app object: <dash.dash.Dash object at 0x...>
    ✓ Found server object: <Flask 'app'>
    ✓ Server is a Flask app instance
    ✓ All checks passed! Ready for gunicorn deployment.

If any check fails, review app.py to ensure:
    1. app = create_app(...) exists at module level
    2. server = app.server exists at module level
"""

import sys
from pathlib import Path

def test_server_import():
    """Test that app.py exports the required server object for gunicorn."""
    
    print("Testing server object for gunicorn compatibility...")
    print("-" * 60)
    
    try:
        # Import the app module
        import app as app_module
        print("✓ Successfully imported app module")
        
        # Check for app object
        if not hasattr(app_module, 'app'):
            print("✗ ERROR: 'app' object not found in app.py")
            print("  Add: app = create_app(...) at module level")
            return False
        print(f"✓ Found app object: {app_module.app}")
        
        # Check for server object
        if not hasattr(app_module, 'server'):
            print("✗ ERROR: 'server' object not found in app.py")
            print("  Add: server = app.server at module level")
            return False
        print(f"✓ Found server object: {app_module.server}")
        
        # Verify server is a Flask app
        from flask import Flask
        if not isinstance(app_module.server, Flask):
            print("✗ ERROR: 'server' is not a Flask app instance")
            return False
        print("✓ Server is a Flask app instance")
        
        # Test that we can get the WSGI app
        wsgi_app = app_module.server.wsgi_app
        print(f"✓ WSGI app accessible: {wsgi_app}")
        
        print("-" * 60)
        print("✓ All checks passed! Ready for gunicorn deployment.")
        print("\nYou can now run:")
        print("  gunicorn app:server --bind 0.0.0.0:8080")
        print("\nOr build the Docker image:")
        print("  docker build -t usda-dashboard:latest .")
        
        return True
        
    except ImportError as e:
        print(f"✗ ERROR: Failed to import app module: {e}")
        print("  Make sure you're in the correct directory")
        print("  and requirements are installed: pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"✗ ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_server_import()
    sys.exit(0 if success else 1)
