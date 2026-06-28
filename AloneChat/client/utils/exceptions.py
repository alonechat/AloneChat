"""Client-side exception classes.

Only exception classes that are actually imported and used in the codebase
should live here. Dead classes (e.g. MessageError, RenderError) that are
never referenced anywhere have been pruned.
"""


class ClientError(Exception):
    """Base exception for all client-side errors."""
