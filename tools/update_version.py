#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Version number updating tool
Support 4 digit (Main.Sub.Patch.Build)
Usage:
  - Default: increment Build and write back
  - --just-show: only print current version
  - --set-version X.Y.Z[.B]: set version (3 or 4 parts)
"""
import os
import re
import argparse
import sys

VERSION_FILE = os.path.join(os.path.dirname(__file__), 'AloneChat', '__init__.py')

def read_content(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_content(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def extract_version(content):
    m = re.search(r'__version__ = "([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)"', content)
    if not m:
        print("Cannot find version number")
        sys.exit(1)
    return m.group(1)

def normalize_parts(parts):
    parts = list(map(int, parts))
    while len(parts) < 4:
        parts.append(0)
    return parts

def main():
    parser = argparse.ArgumentParser(description="Update version in `AloneChat/__init__.py`")
    parser.add_argument("--just-show", action="store_true", default=False, help="Only show current version")
    parser.add_argument("--set-version", type=str, help="Set version to X.Y.Z or X.Y.Z.B")
    args = parser.parse_args()

    if args.just_show and args.set_version:
        raise SystemExit("You can't use both --just-show and --set-version.")

    content = read_content(VERSION_FILE)
    current_version = extract_version(content)
    print(f"Current version: {current_version}")

    if args.just_show:
        return

    if args.set_version:
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){2,3}', args.set_version):
            raise SystemExit("Invalid version format. Use X.Y.Z or X.Y.Z.B")
        parts = normalize_parts(args.set_version.split('.'))
        new_version = '.'.join(map(str, parts))
    else:
        parts = normalize_parts(current_version.split('.'))
        parts[3] += 1
        new_version = '.'.join(map(str, parts))

    new_content = re.sub(
        r'__version__ = "[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?"',
        f'__version__ = "{new_version}"',
        content
    )
    write_content(VERSION_FILE, new_content)
    print(f"Version number updated to {new_version}")

if __name__ == "__main__":
    main()
