"""
Key code mappings and action definitions for input handling.
Maps curses key codes to semantic actions.
"""

try:
    import curses  # type: ignore
except Exception:  # pragma: no cover
    curses = None  # type: ignore
from enum import Enum, auto


class KeyCode:
    """Constants for curses key codes."""
    ENTER = 10
    ENTER_ALT = 13
    BACKSPACE = 8
    BACKSPACE_ALT = 127
    DELETE = curses.KEY_DC if curses is not None else 330
    ESCAPE = 27
    TAB = 9
    SPACE = 32

    # Arrow keys
    UP = curses.KEY_UP if curses is not None else 259
    DOWN = curses.KEY_DOWN if curses is not None else 258
    LEFT = curses.KEY_LEFT if curses is not None else 260
    RIGHT = curses.KEY_RIGHT if curses is not None else 261

    # Page keys
    PAGE_UP = curses.KEY_PPAGE if curses is not None else 339
    PAGE_DOWN = curses.KEY_NPAGE if curses is not None else 338
    HOME = curses.KEY_HOME if curses is not None else 262
    END = curses.KEY_END if curses is not None else 360

    # Function keys
    F1 = curses.KEY_F1 if curses is not None else 265
    F2 = curses.KEY_F2 if curses is not None else 266
    F3 = curses.KEY_F3 if curses is not None else 267
    F4 = curses.KEY_F4 if curses is not None else 268


class InputAction(Enum):
    """Semantic actions that can result from key presses."""
    # Text input
    TYPE_CHAR = auto()
    BACKSPACE = auto()
    SUBMIT = auto()

    # Navigation
    SCROLL_UP = auto()
    SCROLL_DOWN = auto()
    SCROLL_PAGE_UP = auto()
    SCROLL_PAGE_DOWN = auto()
    SCROLL_HOME = auto()
    SCROLL_END = auto()

    # Commands
    QUIT = auto()
    HELP = auto()
    UNKNOWN = auto()
    IGNORE = auto()


# Import curses for key constants
import curses

# Update KeyCode with actual curses values
KeyCode.DELETE = curses.KEY_DC
KeyCode.UP = curses.KEY_UP
KeyCode.DOWN = curses.KEY_DOWN
KeyCode.LEFT = curses.KEY_LEFT
KeyCode.RIGHT = curses.KEY_RIGHT
KeyCode.PAGE_UP = curses.KEY_PPAGE
KeyCode.PAGE_DOWN = curses.KEY_NPAGE
KeyCode.HOME = curses.KEY_HOME
KeyCode.END = curses.KEY_END
KeyCode.F1 = curses.KEY_F1
KeyCode.F2 = curses.KEY_F2
KeyCode.F3 = curses.KEY_F3
KeyCode.F4 = curses.KEY_F4


def get_action_for_key(key: int) -> InputAction:
    """
    Map a key code to an input action.

    Args:
        key: Curses key code

    Returns:
        Corresponding input action
    """
    # noinspection PyUnreachableCode
    match key:
        # Submit/Enter
        case KeyCode.ENTER | KeyCode.ENTER_ALT | curses.KEY_ENTER:
            return InputAction.SUBMIT

        # Backspace
        case KeyCode.BACKSPACE | KeyCode.BACKSPACE_ALT | KeyCode.DELETE | curses.KEY_BACKSPACE:
            return InputAction.BACKSPACE

        # Scrolling
        case KeyCode.UP | curses.KEY_UP:
            return InputAction.SCROLL_UP

        case KeyCode.DOWN | curses.KEY_DOWN:
            return InputAction.SCROLL_DOWN

        case KeyCode.PAGE_UP | curses.KEY_PPAGE:
            return InputAction.SCROLL_PAGE_UP

        case KeyCode.PAGE_DOWN | curses.KEY_NPAGE:
            return InputAction.SCROLL_PAGE_DOWN

        case KeyCode.HOME | curses.KEY_HOME:
            return InputAction.SCROLL_HOME

        case KeyCode.END | curses.KEY_END:
            return InputAction.SCROLL_END

        # Function keys
        case KeyCode.F1 | curses.KEY_F1:
            return InputAction.HELP

        # Escape / Quit
        case KeyCode.ESCAPE:
            return InputAction.QUIT

        # Printable characters
        case k if 0 < k < 256 and chr(k).isprintable():
            return InputAction.TYPE_CHAR

        # Ignore everything else
        case _:
            return InputAction.IGNORE


def is_printable(key: int) -> bool:
    """
    Check if a key code represents a printable character.

    Args:
        key: Key code to check

    Returns:
        True if printable, False otherwise
    """
    return 0 < key < 256 and chr(key).isprintable()


def get_char(key: int) -> str:
    """
    Convert a key code to its character representation.

    Args:
        key: Key code

    Returns:
        Character string
    """
    if is_printable(key):
        return chr(key)
    return ""
