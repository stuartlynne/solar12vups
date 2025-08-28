# Changelog

All notable changes to this project will be documented in this file.

## [0.31] - 2025-08-28
- Add desktop installer utility and CLI flags:
  - `solar12vups --add-desktop-icon [--menu] [--system]` to create Desktop/menu entries.
- Install themed icons at multiple sizes (48/64/128/256) for proper scaling.
- Make icon path resolution robust when running outside the repo or with missing CWD.
- Remove setup.py post-install hook (not executed for wheel installs).
- Add AGENTS.md contributor guide and Makefile helpers for user/system install.
- Update README with Desktop Launcher instructions.

## [0.30] - 2024-07-20
- Initial packaging via setup.py with console script `solar12vups`.

