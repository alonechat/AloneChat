# AloneChat

This project is a simple chat system currently featuring only chat rooms. More elaborate features will be considered
later.

## Origins

Frankly, this project emerged simply because we felt like building something—no grand origin story here.

### Naming

The name carries some irony. "Alone" means solitary.  
What’s "solitary chatting"? Talking to oneself? Exactly.  
During development, we couldn’t conduct large-scale testing.  
Our process: fire up three terminals—one for the server, two for clients—  
then send messages back and forth between clients,  
switching roles to debug and verify functionality.

See? Literally chatting *alone*.

Thus, the name `AloneChat` was born…

### Initial Developers

Well, this part’s straightforward—two middle school students.

- Zhang: Architecture & UI Lead  `<zhang dot chenyun at outlook dot com>`
- Tao: Features & Components Lead  `<tonytao2022 at outlook dot com>`

This arrangement works smoothly for now,  
and we plan to maintain it unless the project faces major changes—  
whether it blows up or fizzles out. Contact us if anything comes up.

## Project Overview

The intro above covers the basics, so no repetition here.

Instead, enjoy some quirky behind-the-scenes tidbits:

1. **Total Reset**: Originally developed in August 2024,  
   the first version was… well, "steaming e-garbage" (Zhang takes the lion’s share of blame).  
   The old repo lived at `alonechat/AloneChat.Frame`.
2. **Reborn on 2025.7.9**: Post-reset, everything’s fresh.  
   New URL: `alonechat/AloneChat`.  
   "Frame" was dropped because separating framework/core failed—  
   now merged for ~~simplicity & clarity~~.

### Features

1. [x] Simple chatroom.
2. [x] `curses`TUI.
3. [ ] Plugins support.
4. [ ] API.

Em, generally, not much now...

### Usage

#### For Users

1. Download packaged clients (see Releases).
2. Launch a terminal.
3. Commands:
    - **To start server**:  
      Windows:
      ```powershell  
      ./AloneChat.exe server --port=<your_port>  
      ```  
      Linux:
      ```bash  
      ./AloneChat server --port=<your_port>  
      ```  
    - **To start client**:  
      Windows:
      ```powershell  
      ./AloneChat.exe client --host=<your_host> --port=<your_port>  
      ```  
      Linux:
      ```bash  
      ./AloneChat client --host=<your_host> --port=<your_port>  
      ```  

#### For Developers

```bash  
git clone https://github.com/alonechat/AloneChat  
cd AloneChat  
python -m pip install -r requirements.txt  
python -m pip install -r requirements-dev.txt  # For packaging  
python . server    # Launch server  
python . client    # Launch client  
python packing.py  # Package to EXE  
```  

### Project Structure

```
./AloneChat/
├── __init__.py
├── core
│   ├── __init__.py
│   ├── client
│   │   ├── __init__.py
│   │   └── command.py
│   ├── message
│   │   ├── __init__.py
│   │   └── protocol.py
│   ├── plugin.py
│   └── server
│       ├── __init__.py
│       └── manager.py
├── plugins
│   └── __init__.py
├── start
│   ├── client.py
│   └── server.py
└── test
    └── test_client.py
```

### Branch Strategy

We use `canary` + `develop` + `master`:

- `canary`: **Highly unstable**. For bleeding-edge testing.  
  Users **MUST** meet *all* criteria:
    - **Understand every line of code** *AND/OR*
    - **Diagnose errors’ root causes** *AND/OR*
    - **Fix most bugs independently**.  
      *STRICTLY LIMITED TO* developers/professionals. Hobbyists—use `develop`.
- `develop`: "Stable"? Nope. But *less chaotic* than `canary`.  
  Hobbyists may experiment here (Python proficiency required—no prebuilt packages).
- `master**: Relatively stable. End-users should use this branch.  
  Not recommended for devs due to slow update cycles.

**User/Branch Compatibility**:

| User Type      | `canary` | `develop` | `master` |  
|----------------|----------|-----------|----------|  
| Developers     | ✅        | ⚠️        | ❌        |  
| Tech Hobbyists | ❌        | ✅         | ⚠️       |  
| End Users      | ❌        | ❌         | ✅        |  

### Packaging

We welcome all developers to package the code! Use `packing.py` after installing deps:

```bash  
python -m pip install -r requirements.txt  
python -m pip install -r requirements-dev.txt  # Packaging tools  
```  

## Contributions

Want to contribute code? **HELL YES!**  
We deeply appreciate *any* input—whether it’s:

- **Proposing features**: Edit README to shape our roadmap!
- **Reporting bugs**: File an issue!
- **Submitting code**: Fork → PR!

## Acknowledgments

Every contributor—however small your edit—earns our fiery gratitude!  
Fix a typo? We’ll salute you with virtual confetti!

## LICENSE

`Apache License Version 2.0`—full text in `LICENSE` file.