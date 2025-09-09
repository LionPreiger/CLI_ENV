#!/usr/bin/env python3
"""
Setup script for Remote Command Server/Client with HTTPS/WSS support
This script installs all required dependencies
"""

import subprocess
import sys
import os

def install_package(package):
    """Install a package using pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    print("=" * 60)
    print("Remote Command Server/Client Setup - HTTPS/WSS Edition")
    print("=" * 60)
    
    # Check if requirements.txt exists
    if os.path.exists("requirements.txt"):
        print("Installing dependencies from requirements.txt...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("✅ All dependencies installed successfully!")
        except subprocess.CalledProcessError:
            print("❌ Failed to install some dependencies. Please check the error messages above.")
            return
    else:
        print("Installing dependencies manually...")
        packages = [
            "flask>=2.0.0",
            "flask-socketio>=5.0.0", 
            "requests>=2.25.0",
            "python-socketio>=5.0.0",
            "cryptography>=3.4.0",
            "urllib3>=1.26.0",
            "eventlet>=0.31.0",
            "websockets>=10.0"
        ]
        
        failed_packages = []
        for package in packages:
            print(f"Installing {package}...")
            if install_package(package):
                print(f"✅ {package} installed successfully")
            else:
                print(f"❌ Failed to install {package}")
                failed_packages.append(package)
        
        if failed_packages:
            print(f"\n❌ Failed to install: {', '.join(failed_packages)}")
            print("Please install these manually or check your internet connection.")
            return
        else:
            print("\n✅ All dependencies installed successfully!")
    
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print("🔒 Security Features Enabled:")
    print("  - HTTPS communication")
    print("  - WSS (WebSocket Secure) streaming")
    print("  - Self-signed certificate generation")
    print("  - SSL certificate validation options")
    print("\n📋 Usage:")
    print("  Original Server: python VM_client.py")
    print("  Original Client: python Host_server.py")
    print("  New VM Client v2: python vmclientv2.py [vm_id]")
    print("\n🆕 New VM Client v2 Features:")
    print("  - Connects to external WebSocket server")
    print("  - Endpoint: 217.154.254.231:9000/api/vm/{vmid}/ws")
    print("  - Automatic VM ID generation if not provided")
    print("  - Auto-reconnection on connection loss")
    print("  - Real-time command execution streaming")
    print("\n⚠️  Note: When using HTTPS with self-signed certificates,")
    print("   browsers may show security warnings. This is normal")
    print("   and safe for trusted networks.")
    print("=" * 60)

if __name__ == "__main__":
    main()
