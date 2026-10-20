# Contributing

Petal currently uses Python with GTK4, Cairo, and gtk4-layer-shell. Use Python 3.11+ with the runtime dependencies listed in README.md. pypdf is vendored; preserve its upstream license and update the pinned audit requirement when changing it.

Run unit/conversion tests from the project root:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q petal
```

These tests generate their own media, verify output contents and source hashes, and check cancellation, collisions, unsafe archives, preferences, launchers, and package integrity. The office test is skipped when no compatible LibreOffice is installed.

Native tests need a Wayland session. Each uses an isolated application ID and temporary state, and does not control the production app. Installer execution is mocked in software-flow tests; they never install packages.

```sh
./scripts/run_native_checks.sh ./work/native
python3 tests/verify_software.py --output-dir ./work/software
```

The latter exercises the missing-office UI and expects office conversion to be unavailable on the normal test PATH. Conversion tests separately cover a present office engine. Native picker tests use real opening/cancellation with a supplied selected-file model for callback tests; this does not certify every portal implementation.

Check critical Python errors, medium/high security findings, and the pinned vendored dependency with `ruff check`, `bandit -r petal -ll`, and `pip-audit --no-deps --disable-pip -r requirements-audit.txt`. Use an isolated environment for these tools. Do not install audit tools into the system Python.

Build reproducible archives with `python3 scripts/build_release.py`. Only allowlisted source/assets/docs are included. State, logs, caches, Git metadata, and private reference media are excluded. Release verification should include extracted-package launch, desktop-entry validation, hash checks, and a secrets/path review.

For UI changes, follow docs/ux.md and verify keyboard navigation, empty states, cancellation, larger text, and reduced motion. Keep the wheel and Settings separate, preserve individual layer namespaces, and never add program recommendations or automatic downloads without changing the documented user-choice behavior.
