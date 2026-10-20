# Changelog

## 0.6.0 — 2026-10-20

First public release as **Petal**, an unofficial Linux port/reimplementation of Tangerine for macOS.

- New, independently generated Petal rosette logo and complete app/tray/launcher branding.
- Empty leaf clicks now open a file picker and retain compatible action choices without immediately starting a conversion.
- Explicit keyboard focus while the wheel is visible; capture-phase mode keys, already-held modifier detection, and drag-event modifier handling. Hidden wheels release the keyboard; passive drag previews do not grab it.
- Native right-click / Shift+F10 action menu, keyboard file opening, accessible action names, visible focus, readable primary-button text, and scrolling layouts for larger text.
- First-launch app/appearance/workflow setup and neutral software lists with external-program choices. No program download is preselected.
- Optional, reviewed Arch/CachyOS package installation with interactive authentication and capability checks afterward.
- Updated vendored pypdf from 6.10.2 to 6.21.1 after dependency advisories were detected in the release audit.
- Headless help/version/diagnostics, guarded desktop-launcher installation, reproducible archives, tests, and CI.
