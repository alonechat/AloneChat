<a name="v1.5.0"></a>

## [v1.5.0](https://github.com/alonechat/AloneChat/compare/v1.0.1...v1.5.0) (2025-08-06)

### Feat

* Introduce our WebUI!
  * Add NOTICE file.
  * Update URL params usage and documents...
  * Update webUI
  * New FastAPI API is coming!

  ### Fix

* Fix typos
  * Fix typos and some refactored small bugs.
  * Fix double-sending bug and i18n comments
  * Fix typos
  * Fix typos with noinspection comment...
  * Fix typos and update some content to fit some latest updates.
  * Fix typo: `client_parser` to `test_parser`
  * Fix typos

  ### Update

* Update test

  ### Pull Requests

* Merge pull request [#9](https://github.com/alonechat/AloneChat/issues/9) from alonechat/develop
  * Merge pull request [#8](https://github.com/alonechat/AloneChat/issues/8) from alonechat/canary

<a name="v1.0.1"></a>

## v1.0.1 (2025-07-28)

### Docs

* Update the project directory structure in the README

  ### Feat

* Update plugin system
  * Update TUI to improve delete logic...in Windows
  * Update client UI option to support 'text' mode in main execution
  * Add CursesClient for TUI support and update client initialization
  * Enhance documentation and structure across modules; add entry points for client and server
  * Update plugin system
  * Add developing requirements
  * add packing script to automate PyInstaller build process
  * Update client and server
  * Implement the basic functions of the chat system

  ### Refactor

* directory rename: network to message; update server module's __all__
  * Remove old WebSocketManager indexes
  * Remove old WebSocket client and server implementations

  ### Update

* Update packing.py, add cleaner command line option.
  * Update README.md and README-zh.md, and add some important information.
  * Update client to avoid Windows user don't know or cannot install curses.
  * Update README.md, add email of tony tao
  * Update README.md and add i18n works

  ### Pull Requests

* Merge pull request [#6](https://github.com/alonechat/AloneChat/issues/6) from alonechat/develop
  
  