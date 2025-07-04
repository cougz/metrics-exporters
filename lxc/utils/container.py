"""Utility functions for container identification"""
import re
import os


def extract_container_id():
    """Extract LXC container ID from various sources"""
    
    # Method 1: From device name in df output
    try:
        import subprocess
        result = subprocess.run(["df", "/"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                device = lines[1].split()[0]
                # Look for pattern like "subvol-XXXXX-disk-X"
                match = re.search(r'subvol-(\d+)-disk-\d+', device)
                if match:
                    return match.group(1)
    except:
        pass
    
    # Method 2: From cgroup path
    try:
        with open("/proc/self/cgroup", "r") as f:
            for line in f:
                # Look for lxc container ID in cgroup path
                match = re.search(r'/lxc/(\d+)', line)
                if match:
                    return match.group(1)
    except:
        pass
    
    # Method 3: From hostname if it follows container pattern
    try:
        import socket
        hostname = socket.gethostname()
        match = re.search(r'(\d+)', hostname)
        if match and len(match.group(1)) >= 3:  # Assume container IDs are at least 3 digits
            return match.group(1)
    except:
        pass
    
    return None
