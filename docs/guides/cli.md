[Documentation](../README.md) / Command line and storage

# Command line and storage

```sh
./petal-run --help
./petal-run --version
./petal-run --tray
./petal-run --settings
./petal-run --software
./petal-run --setup
./petal-run --check
./petal-run --doctor
./petal-run convert ./photo.png --to webp
./petal-run convert ./clip.mov --to mp4 --output-dir ./converted
./petal-run --quit
```

`--check`, `--doctor`, `--help`, `--version`, and conversions do not require a desktop display. `--doctor` exits 1 when a feature is unavailable, which is expected if optional engines are absent. `--setup` reopens first-launch preferences.

## Local storage

Settings and local history live in `$XDG_STATE_HOME/petal`, normally `~/.local/state/petal`. Override with `PETAL_STATE_DIR`. History contains local input/output paths; it is never uploaded and is excluded from releases. `PETAL_LIBREOFFICE` and `PETAL_ENGINE_PATHS` can specify existing engines; validated Settings choices are preferred. No account, telemetry, or conversion-upload service is included. Optional package downloads use the distribution's configured repositories.
