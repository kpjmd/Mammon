#!/usr/bin/env python3
"""Initial setup script for MAMMON.

This script helps with first-time setup of MAMMON including:
- Creating .env file from template
- Initializing database
- Verifying dependencies
"""

import os
import sys
from pathlib import Path


def main() -> None:
    """Run initial setup."""
    print("🚀 MAMMON Setup Script")
    print("=" * 50)

    # Check if .env exists
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file already exists")
    else:
        print("📝 Creating .env file from template...")
        env_example = Path(".env.example")
        if env_example.exists():
            env_file.write_text(env_example.read_text())
            print("✅ Created .env file")
            print("⚠️  IMPORTANT: Edit .env and add your API keys!")
        else:
            print("❌ .env.example not found!")
            sys.exit(1)

    # Check Python version
    if sys.version_info < (3, 11):
        print("❌ Python 3.11+ required")
        sys.exit(1)
    else:
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")

    # Check if poetry is installed
    try:
        import poetry
        print("✅ Poetry installed")
    except ImportError:
        print("⚠️  Poetry not found in Python path (may be installed globally)")

    print("\n" + "=" * 50)
    print("Next steps:")
    print("1. Edit .env file with your API keys")
    print("2. Run: poetry install")
    print("3. Run: poetry run python -m pytest")
    print("4. Run: poetry run streamlit run dashboard/app.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
