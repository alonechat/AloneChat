"""
A build script for AloneChat application.
Creates standalone executable using PyInstaller.
"""

import os
import shutil
import subprocess


def build():
    """
    Build the AloneChat application into a standalone executable using PyInstaller.

    This script uses PyInstaller to package the application into a single executable file.
    It can be run from the command line to create the build.
    """
    # Configuration for PyInstaller build
    main_script = "__main__.py"  # Entry point of the application

    # PyInstaller command configuration
    command = [
        "pyinstaller",
        "--onefile",  # Create a single executable file
        "--clean",  # Clean up temporary files after build
        # "--windowed",       # Uncomment to hide the console window (GUI mode)
        main_script
    ]

    # Execute PyInstaller command to build the executable
    subprocess.run(command)


def clean():
    """
    Clean up the build artifacts created by PyInstaller.

    This function removes the 'build' and 'dist' directories, as well as the '__pycache__' directory
    and the generated executable file.
    """

    # Directories to remove
    directories = ['build', '__pycache__']

    for directory in directories:
        if os.path.exists(directory):
            shutil.rmtree(directory)

    if os.path.exists('__main__.spec'):
        os.remove('__main__.spec')  # Remove the PyInstaller spec file if it exists

    for root, dirs, files in os.walk(".", topdown=False):
        for name in dirs:
            if name == '__pycache__':
                shutil.rmtree(os.path.join(root, name))


def preprocessing():
    """
    Preprocessing step before building the application.

    This function can be used to perform any necessary preprocessing tasks
    such as cleaning up old build artifacts or preparing resources.
    """
    clean()  # Clean up previous build artifacts
    # Additional preprocessing tasks can be added here
    if os.path.exists('dist'):
        shutil.rmtree('dist')  # Remove existing dist directory if it exists


def postprocessing():
    """
    Postprocessing step after building the application.

    This function can be used to perform any necessary postprocessing tasks
    such as moving the executable to a specific location or cleaning up temporary files.
    """
    # Move the built executable to a desired location if needed
    # For example, move it to a 'bin' directory
    clean()
    # Clean up the dist directory after moving
    shutil.move('dist/__main__.exe', 'dist/AloneChat.exe')


if __name__ == "__main__":
    preprocessing()
    build()  # Build the application
    postprocessing()
