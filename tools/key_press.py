#!/usr/bin/env python3
import time
import curses

def main(stdscr):
    """
    A test script to display the curses key code for any key pressed.
    """
    # --- Curses Initialization ---
    # Turn off echoing of keys to the screen
    curses.noecho()
    # React to keys instantly, don't wait for the Enter key
    curses.cbreak()
    # Enable special keys (like arrow keys, F-keys, etc.) to be recognized
    stdscr.keypad(True)

    # --- Main Loop ---
    while True:
        # Clear the screen for the new output
        stdscr.clear()

        # Display instructions
        stdscr.addstr(0, 0, "Press any key to see its code (or '^C' to quit).")
        stdscr.addstr(1, 0, "Try letters, numbers, arrow keys, F1-F12, Page Up/Down, etc.")

        # Wait for a key press and get its integer code
        key_code = stdscr.getch()

        # Check for the 'q' key to quit
        # if key_code == ord('q'):
        #     break

        # Get the human-readable name of the key from its code
        # keyname() returns a byte string, so we decode it
        key_name = curses.keyname(key_code).decode('utf-8')

        # Format the output string for clarity
        output_line = f"Key Code: {key_code:<5} | Key Name: '{key_name}'"

        # Print the result to the screen
        stdscr.addstr(3, 0, output_line)

        # Refresh the screen to show the new text
        stdscr.refresh()

        # Pause briefly to allow the user to see the output
        stdscr.addstr(4, 0, "Press any key to continue...")
        stdscr.refresh()
        stdscr.getch()  # Wait for another key press before continuing

# This is the standard, safe way to run a curses application.
# It handles initializing curses, calling your main function,
# and then restoring the terminal to its original state even if an error occurs.
if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass