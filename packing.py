"""
A build script for AloneChat application.
Creates standalone executable using PyInstaller.
"""

import subprocess

# Configuration for PyInstaller build
main_script = "__main__.py"  # Entry point of the application

# PyInstaller command configuration
command = [
    "pyinstaller",
    "--onefile",  # Create a single executable file
    # "--windowed", # Uncomment to hide the console window (GUI mode)
    main_script
]

# Execute PyInstaller command to build the executable
subprocess.run(command)