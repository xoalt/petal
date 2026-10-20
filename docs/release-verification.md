# Release verification — 0.1.0-beta.2

Verified on 2026-10-20 on MangoWM / Wayland.

- 81 unit/conversion/release tests: 80 passed locally, one office conversion test skipped because this sandbox cannot create the required IPC path. CI runs the complete suite with an installed office engine.
- Beta 2 native editor checks: 33 passed, including actual GTK gesture signals, synchronized rectangle fields, crop export dimensions, PDF page order, batch order, and source hashes.
- Earlier local native checks: 31 onboarding, 17 editors, 22 software, 38 ux, 12 desktop, all passed.
- Critical Python lint, compilation, shell syntax, and desktop-entry validation passed.
- No medium/high Bandit findings. The pinned vendored pypdf 6.21.1 has no known advisories in the release-time pip-audit result. Its 60 module files match the upstream wheel; the wheel hash is pinned. Host conversion programs and GTK are supplied by the distribution and are outside that scan.
- The PDF library was upgraded after 41 advisories were found against the previous bundled version. Conversion and PDF tests passed after the upgrade.
- Reproducible ZIP and tar.gz construction, per-file hashes, executable launcher mode, extracted-package checks, user-state exclusion, and managed desktop-launcher installation/removal are verified.
- Modifier checks cover both keyboard sides, capture-phase event delivery, held modifiers, drag-event state, latched modes, explicit layer keyboard focus, release on hide, and passive preview behavior.
- Native screenshots use generated test files, including the new drag-crop, watermark, and PDF-page editors. No private user files, history, settings, press assets, or original icons are published.

Installer transactions are mocked during UI tests: no packages were installed on the user's system. Sample checks do not certify every format combination or malformed input. Native picker tests use actual opening/cancellation and supply a selected-file model for callback behavior, which does not certify every desktop portal. CI uses GTK local pickers for synthetic response tests. Artificial picker responses can produce GTK portal cleanup warnings; a later local synthetic-picker run encountered a GTK segmentation fault. Independent headless native checks run in CI. Full screen-reader and on-screen-keyboard testing is not claimed.

GitHub CI runs conversion/safety tests with an installed office engine and native checks on a separate headless Wayland compositor. MangoWM-specific layer focus is verified locally; the headless compositor uses ordinary-window fallback. See the repository's Actions page for the checks on the published commit.

Machine-readable details are in [release-verification.json](release-verification.json).
