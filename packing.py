import subprocess

# Install PyInstaller if not already installed by using pip install -r requirements-dev.txt
main_script = "__main__.py"  

command = [
    "pyinstaller",
    "--onefile",
    # "--windowed",  
    main_script
]

# Run PyInstaller
subprocess.run(command)