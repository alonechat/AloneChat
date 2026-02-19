"""
Components using sv_ttk (Sun Valley theme) - modern UI components.
"""
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable


class WinUI3Entry(ttk.Frame):
    """Modern entry field with icon support and improved styling."""
    
    def __init__(self, parent, label: str = "", placeholder: str = "",
                 password: bool = False, width: int = 40, 
                 icon: str = "", **kwargs):
        super().__init__(parent, **kwargs)
        
        self.placeholder = placeholder
        self._show_password = password
        self._is_password = password
        
        if label:
            label_frame = ttk.Frame(self)
            label_frame.pack(fill="x", pady=(0, 6))
            
            self.label_widget = ttk.Label(label_frame, text=label, font=("Segoe UI", 10))
            self.label_widget.pack(side="left")
        
        entry_container = ttk.Frame(self)
        entry_container.pack(fill="x")
        entry_container.configure(style="Card.TFrame")
        
        if icon:
            icon_label = ttk.Label(entry_container, text=icon, font=("Segoe UI", 12))
            icon_label.pack(side="left", padx=(12, 8), pady=10)
        
        self.entry = ttk.Entry(
            entry_container, 
            width=width, 
            show="●" if password else "",
            font=("Segoe UI", 11)
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(12 if not icon else 0, 12), pady=10)
        
        if password:
            self.toggle_btn = ttk.Button(
                entry_container,
                text="👁",
                width=3,
                command=self._toggle_password_visibility
            )
            self.toggle_btn.pack(side="right", padx=(0, 8), pady=8)
        
        self._setup_focus_effects(entry_container)
    
    def _setup_focus_effects(self, container):
        def on_focus_in(event):
            container.configure(style="Focus.TFrame")
        
        def on_focus_out(event):
            container.configure(style="Card.TFrame")
        
        self.entry.bind("<FocusIn>", on_focus_in)
        self.entry.bind("<FocusOut>", on_focus_out)
    
    def _toggle_password_visibility(self):
        if self._show_password:
            self.entry.configure(show="")
            self.toggle_btn.configure(text="🔒")
        else:
            self.entry.configure(show="●")
            self.toggle_btn.configure(text="👁")
        self._show_password = not self._show_password
    
    def get(self) -> str:
        try:
            return self.entry.get()
        except tk.TclError:
            return ""
    
    def set(self, value: str):
        try:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, value)
        except tk.TclError:
            pass
    
    def focus(self):
        try:
            self.entry.focus_set()
        except tk.TclError:
            pass


class LoadingButton(ttk.Frame):
    """Button with loading state indicator."""
    
    def __init__(self, parent, text: str, command: Callable, 
                 primary: bool = False, **kwargs):
        super().__init__(parent, **kwargs)
        
        self._text = text
        self._command = command
        self._loading = False
        self._original_style = "Accent.TButton" if primary else "TButton"
        
        self.button = ttk.Button(
            self, 
            text=text, 
            command=self._handle_click,
            style=self._original_style
        )
        self.button.pack(fill="both", expand=True)
    
    def _handle_click(self):
        if not self._loading:
            self._command()
    
    def start_loading(self):
        self._loading = True
        self.button.configure(text="● ● ●", state="disabled")
        self._animate_dots()
    
    def _animate_dots(self):
        if not self._loading:
            return
        current = self.button.cget("text")
        if current == "● ● ●":
            self.button.configure(text="● ●  ")
        elif current == "● ●  ":
            self.button.configure(text="●   ●")
        else:
            self.button.configure(text="● ● ●")
        if self._loading:
            self.after(400, self._animate_dots)
    
    def stop_loading(self):
        self._loading = False
        self.button.configure(text=self._text, state="normal")
    
    def set_error(self, error_text: str):
        self._loading = False
        self.button.configure(text=f"✕ {error_text}", style="Danger.TButton")
        self.after(2000, self._reset)
    
    def _reset(self):
        self.button.configure(text=self._text, style=self._original_style, state="normal")


class StatusMessage(ttk.Frame):
    """Animated status message display."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.label = ttk.Label(self, text="", font=("Segoe UI", 10), wraplength=300)
        self.label.pack(pady=8)
        self._hide_job = None
    
    def show_success(self, message: str, duration: int = 3000):
        self._show(message, "success")
        self._schedule_hide(duration)
    
    def show_error(self, message: str, duration: int = 4000):
        self._show(message, "error")
        self._schedule_hide(duration)
    
    def show_info(self, message: str, duration: int = 3000):
        self._show(message, "info")
        self._schedule_hide(duration)
    
    def _show(self, message: str, msg_type: str):
        if self._hide_job:
            self.after_cancel(self._hide_job)
        
        icons = {"success": "✓", "error": "✕", "info": "ℹ"}
        colors = {"success": "#10b981", "error": "#ef4444", "info": "#3b82f6"}
        
        self.label.configure(
            text=f"{icons.get(msg_type, '')} {message}",
            foreground=colors.get(msg_type, "#6b7280")
        )
    
    def _schedule_hide(self, duration: int):
        self._hide_job = self.after(duration, self.hide)
    
    def hide(self):
        self.label.configure(text="")


class WinUI3ScrollableFrame(ttk.Frame):
    """Scrollable frame using ttk with sv_ttk theme."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.content = ttk.Frame(self.canvas)
        self.content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self._setup_scrolling()
    
    def _setup_scrolling(self):
        def on_content_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            canvas_width = self.canvas.winfo_width()
            self.canvas.itemconfig(self.content_window, width=canvas_width)
        
        def on_canvas_configure(event):
            self.canvas.itemconfig(self.content_window, width=event.width)
        
        self.content.bind('<Configure>', on_content_configure)
        self.canvas.bind('<Configure>', on_canvas_configure)
        
        def on_mousewheel(event):
            try:
                if self.canvas.winfo_exists():
                    self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except tk.TclError:
                pass
        
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)
    
    def scroll_to_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)
    
    def scroll_to_widget(self, widget: tk.Widget):
        try:
            self.canvas.update_idletasks()
            y = widget.winfo_y()
            h = max(1, self.content.winfo_height())
            pos = max(0.0, min(1.0, (y - 20) / h))
            self.canvas.yview_moveto(pos)
        except Exception:
            pass


class CollapsibleSection(ttk.Frame):
    """Collapsible section with smooth animation."""
    
    def __init__(self, parent, title: str, **kwargs):
        super().__init__(parent, **kwargs)
        
        self._expanded = False
        self._content_frame = None
        
        header = ttk.Frame(self)
        header.pack(fill="x")
        
        self.toggle_btn = ttk.Button(
            header, 
            text=f"▶ {title}",
            command=self.toggle,
            style="Toolbutton"
        )
        self.toggle_btn.pack(side="left", fill="x", expand=True)
    
    def toggle(self):
        if self._expanded:
            self.collapse()
        else:
            self.expand()
    
    def expand(self):
        self._expanded = True
        self.toggle_btn.configure(text=f"▼ {self.toggle_btn.cget('text')[2:]}")
        if self._content_frame:
            self._content_frame.pack(fill="x", pady=(8, 0))
    
    def collapse(self):
        self._expanded = False
        self.toggle_btn.configure(text=f"▶ {self.toggle_btn.cget('text')[2:]}")
        if self._content_frame:
            self._content_frame.pack_forget()
    
    def set_content(self, content: ttk.Frame):
        self._content_frame = content
