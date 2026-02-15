"""
Exception classes for the plugin system.

This module defines all custom exceptions used throughout the plugin system.
"""


class PluginError(Exception):
    """Base exception for all plugin-related errors."""
    
    def __init__(self, message: str, plugin_name: str = None):
        """
        Initialize plugin error.
        
        Args:
            message: Error message
            plugin_name: Name of the plugin that caused the error
        """
        self.plugin_name = plugin_name
        super().__init__(message)
    
    def __str__(self) -> str:
        if self.plugin_name:
            return f"[{self.plugin_name}] {super().__str__()}"
        return super().__str__()


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load."""
    pass


class PluginInitError(PluginError):
    """Raised when a plugin fails to initialize."""
    pass


class PluginDependencyError(PluginError):
    """Raised when a plugin dependency cannot be resolved."""
    
    def __init__(self, plugin_name: str, missing_dependency: str, message: str = None):
        """
        Initialize dependency error.
        
        Args:
            plugin_name: Name of the plugin with missing dependency
            missing_dependency: Name of the missing dependency
            message: Optional custom message
        """
        self.missing_dependency = missing_dependency
        if message is None:
            message = f"Missing required dependency: {missing_dependency}"
        super().__init__(message, plugin_name)


class PluginCircularDependencyError(PluginError):
    """Raised when circular dependencies are detected."""
    
    def __init__(self, plugin_name: str, dependency_chain: list):
        """
        Initialize circular dependency error.
        
        Args:
            plugin_name: Name of the plugin with circular dependency
            dependency_chain: List of plugins in the circular chain
        """
        self.dependency_chain = dependency_chain
        chain_str = " -> ".join(dependency_chain)
        message = f"Circular dependency detected: {chain_str}"
        super().__init__(message, plugin_name)


class PluginNotFoundError(PluginError):
    """Raised when a requested plugin cannot be found."""
    pass


class PluginStateError(PluginError):
    """Raised when a plugin is in an invalid state for the requested operation."""
    pass


class PluginValidationError(PluginError):
    """Raised when a plugin fails validation."""
    pass


class PluginRegistrationError(PluginError):
    """Raised when a plugin cannot be registered."""
    pass


class PluginConfigError(PluginError):
    """Raised when a plugin has invalid configuration."""
    pass
