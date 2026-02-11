"""
GUI client with integrated command-line interface for AloneChat.
Provides a GUI window with a command-line style interface.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Optional, Callable

from .client_base import Client
from .cli import CLISelector, GUIBackend, Command, CommandType
from .utils import DEFAULT_HOST, DEFAULT_API_PORT

__all__ = ['GUICLIClient']


class GUICLIClient(Client):
    """
    GUI client with integrated command-line interface.
    Provides a terminal-like experience in a GUI window.
    """
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_API_PORT,
        ui_type: str = "gui"
    ):
        """
        Initialize the GUI CLI client.

        Args:
            host: Server hostname
            port: Server port
            ui_type: UI type preference
        """
        super().__init__(host, port)
        self.ui_type = ui_type
        
        # GUI components
        self.root: Optional[tk.Tk] = None
        self.output_text: Optional[scrolledtext.ScrolledText] = None
        self.input_entry: Optional[tk.Entry] = None
        
        # CLI components
        self.backend: Optional[GUIBackend] = None
        self.selector: Optional[CLISelector] = None
        
        # Callbacks
        self._input_callback: Optional[Callable[[str], None]] = None
        
    def _create_ui(self) -> None:
        """Create the GUI interface."""
        self.root = tk.Tk()
        self.root.title("AloneChat - CLI Mode")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Configure grid
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Output area (scrolled text)
        self.output_text = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            font=("Consolas", 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            padx=10,
            pady=10
        )
        self.output_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.output_text.config(state=tk.DISABLED)
        
        # Input frame
        input_frame = ttk.Frame(self.root)
        input_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        input_frame.grid_columnconfigure(1, weight=1)
        
        # Prompt label
        prompt_label = ttk.Label(input_frame, text=">", font=("Consolas", 11))
        prompt_label.grid(row=0, column=0, padx=(5, 0))
        
        # Input entry
        self.input_entry = tk.Entry(
            input_frame,
            font=("Consolas", 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            relief=tk.FLAT
        )
        self.input_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.input_entry.focus_set()
        
        # Bind events
        self.input_entry.bind('<Return>', self._on_input_submit)
        self.input_entry.bind('<Up>', self._on_history_up)
        self.input_entry.bind('<Down>', self._on_history_down)
        self.root.bind('<Control-c>', lambda e: self._on_exit())
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)
        
        # History
        self._history: list[str] = []
        self._history_index = 0
        
    def _on_input_submit(self, event=None) -> None:
        """Handle input submission."""
        text = self.input_entry.get().strip()
        if text:
            # Add to history
            self._history.append(text)
            self._history_index = len(self._history)
            
            # Display input
            self._append_output(f"> {text}\n")
            
            # Clear input
            self.input_entry.delete(0, tk.END)
            
            # Process command
            if self._input_callback:
                self._input_callback(text)
    
    def _on_history_up(self, event=None) -> None:
        """Navigate up in history."""
        if self._history and self._history_index > 0:
            self._history_index -= 1
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, self._history[self._history_index])
    
    def _on_history_down(self, event=None) -> None:
        """Navigate down in history."""
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, self._history[self._history_index])
        else:
            self._history_index = len(self._history)
            self.input_entry.delete(0, tk.END)
    
    def _append_output(self, text: str) -> None:
        """Append text to output area."""
        if self.output_text:
            self.output_text.config(state=tk.NORMAL)
            self.output_text.insert(tk.END, text)
            self.output_text.see(tk.END)
            self.output_text.config(state=tk.DISABLED)
    
    def _display_output(self, message: str) -> None:
        """Display output message."""
        self._append_output(message + "\n")
    
    def _on_exit(self) -> None:
        """Handle exit."""
        if self.selector:
            self.selector.running = False
        if self.root:
            self.root.destroy()
    
    def _init_cli(self) -> None:
        """Initialize CLI components."""
        # Create GUI backend
        self.backend = GUIBackend()
        self.backend.set_callbacks(
            input_callback=self._on_cli_input,
            output_callback=self._display_output
        )
        
        # Create selector
        self.selector = CLISelector(
            ui_backend=self.backend,
            host=self.host,
            port=self.port,
            ui_type=self.ui_type
        )
        
        # Set input callback
        self._input_callback = self.selector.process_command
        
        # Override exit handler to close GUI
        self.selector.executor.parser.register_handler(
            CommandType.EXIT,
            self._handle_exit
        )
        self.selector.executor.parser.register_handler(
            CommandType.QUIT,
            self._handle_exit
        )
    
    def _on_cli_input(self, text: str) -> None:
        """Handle CLI input from GUI."""
        # This is called by the backend when input is submitted
        pass
    
    def _handle_exit(self, cmd: Command) -> str:
        """Handle exit command."""
        self.root.after(0, self._on_exit)
        return "Goodbye!"
    
    def run(self) -> None:
        """Run the GUI CLI client."""
        # Create UI
        self._create_ui()
        
        # Initialize CLI
        self._init_cli()
        
        # Show welcome
        welcome = f"""
╔══════════════════════════════════════╗
║     Welcome to AloneChat Client      ║
╚══════════════════════════════════════╝

Current settings:
  Server: {self.selector.executor.host}:{self.selector.executor.port}
  UI Type: {self.selector.executor.ui_type}

Type 'help' for available commands or 'connect' to start.

Shortcuts:
  Ctrl+C  - Exit
  Up/Down - Command history
"""
        self._display_output(welcome)
        
        # Start main loop
        self.root.mainloop()


class EnhancedGUICLIClient(GUICLIClient):
    """
    Enhanced GUI CLI client with additional features.
    Includes command highlighting and better visual feedback.
    """
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_API_PORT,
        ui_type: str = "gui"
    ):
        """Initialize enhanced GUI CLI client."""
        super().__init__(host, port, ui_type)
        
        # Tag configurations
        self._tags = {
            'command': {'foreground': '#569cd6', 'font': ('Consolas', 11, 'bold')},
            'error': {'foreground': '#f44747'},
            'success': {'foreground': '#4ec9b0'},
            'info': {'foreground': '#ce9178'},
            'prompt': {'foreground': '#c586c0'},
        }
    
    def _create_ui(self) -> None:
        """Create enhanced GUI interface."""
        super()._create_ui()
        
        # Configure tags for syntax highlighting
        if self.output_text:
            for tag_name, config in self._tags.items():
                self.output_text.tag_configure(tag_name, **config)
    
    def _append_output(self, text: str, tag: Optional[str] = None) -> None:
        """Append text with optional tag."""
        if self.output_text:
            self.output_text.config(state=tk.NORMAL)
            if tag:
                self.output_text.insert(tk.END, text, tag)
            else:
                self.output_text.insert(tk.END, text)
            self.output_text.see(tk.END)
            self.output_text.config(state=tk.DISABLED)
    
    def _display_output(self, message: str) -> None:
        """Display output with highlighting."""
        lines = message.split('\n')
        for line in lines:
            # Determine tag based on content
            tag = None
            lower_line = line.lower()
            
            if any(cmd in lower_line for cmd in ['error', 'failed', 'invalid']):
                tag = 'error'
            elif any(cmd in lower_line for cmd in ['success', 'connected', 'welcome']):
                tag = 'success'
            elif line.startswith('>'):
                tag = 'prompt'
            elif line.startswith('  '):
                tag = 'info'
            
            self._append_output(line + '\n', tag)
