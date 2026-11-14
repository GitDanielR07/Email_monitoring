#!/usr/bin/env python3
"""
Quick setup validator for Gmail Push Notifications
Checks if all prerequisites are met before running monitor_email_push.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Run from the project root so relative paths (config/, src/, .env) resolve.
os.chdir(Path(__file__).resolve().parent.parent)

# Fix encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def check_env_variables():
    """Check if all required environment variables are set."""
    print("\n📋 Checking Environment Variables...")
    
    load_dotenv()
    
    required_vars = {
        "DISCORD_WEBHOOK_EMAIL": "Discord webhook URL",
        "STUDENT_EMAIL": "Your Gmail address",
        "GOOGLE_CLOUD_PROJECT": "Google Cloud Project ID",
        "PUBSUB_TOPIC": "Pub/Sub topic name",
        "PUBSUB_SUBSCRIPTION": "Pub/Sub subscription name",
    }
    
    optional_vars = {
        "GOOGLE_APPLICATION_CREDENTIALS": "Service account JSON path (optional)",
        "DISCORD_MENTION_ID": "Discord user ID for mentions (optional)",
    }
    
    missing = []
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: {value[:40]}...")
        else:
            print(f"  ❌ {var}: NOT SET - {description}")
            missing.append(var)
    
    print("\n  Optional variables:")
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: Configured")
        else:
            print(f"  ⚪ {var}: Not set (optional)")
    
    return len(missing) == 0, missing


def check_files():
    """Check if all required files exist."""
    print("\n📁 Checking Files...")
    
    required_files = {
        "config/credentials.json": "Gmail API credentials",
        "requirements.txt": "Python dependencies",
        "src/monitor_email_push.py": "Push notification monitor",
    }
    
    optional_files = {
        "config/token.json": "Gmail OAuth token",
        "config/service-account-key.json": "Pub/Sub service account key",
    }
    
    missing = []
    for file, description in required_files.items():
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file}: MISSING - {description}")
            missing.append(file)
    
    print("\n  Optional files:")
    for file, description in optional_files.items():
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ⚪ {file}: Not set (optional)")
    
    return len(missing) == 0, missing


def check_packages():
    """Check if all required Python packages are installed."""
    print("\n📦 Checking Python Packages...")
    
    required_packages = {
        "google.cloud.pubsub_v1": "google-cloud-pubsub",
        "flask": "flask",
        "google.auth": "google-auth",
        "google.oauth2": "google-oauth2",
        "googleapiclient": "google-api-python-client",
        "dotenv": "python-dotenv",
        "requests": "requests",
        "bs4": "beautifulsoup4",
    }
    
    missing = []
    for module, package in required_packages.items():
        try:
            __import__(module)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}: NOT INSTALLED")
            missing.append(package)
    
    return len(missing) == 0, missing


def main():
    print("=" * 70)
    print("Gmail Push Notifications - Setup Validator")
    print("=" * 70)
    
    all_good = True
    missing_packages = []
    
    # Check environment variables
    env_ok, missing_env = check_env_variables()
    all_good = all_good and env_ok
    
    # Check files
    files_ok, missing_files = check_files()
    all_good = all_good and files_ok
    
    # Check packages
    pkg_ok, missing_packages = check_packages()
    all_good = all_good and pkg_ok
    
    # Summary
    print("\n" + "=" * 70)
    if all_good:
        print("✅ ALL CHECKS PASSED!")
        print("\nYou can now run:")
        print("  python src/monitor_email_push.py   (or build the exe: python build.py)")
        return 0
    else:
        print("❌ SETUP INCOMPLETE")
        print("\nFix the following issues:")
        
        if missing_env:
            print(f"\n1. Add missing environment variables to .env:")
            for var in missing_env:
                print(f"   - {var}")
        
        if missing_files:
            print(f"\n2. Create missing files:")
            for file in missing_files:
                print(f"   - {file}")
        
        if missing_packages:
            print(f"\n3. Install missing Python packages:")
            print(f"   pip install {' '.join(missing_packages)}")
        
        print("\nSee PUSH_NOTIFICATION_SETUP.md for detailed instructions")
        return 1


if __name__ == "__main__":
    sys.exit(main())
