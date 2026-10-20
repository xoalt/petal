[Documentation](../README.md) / Conversion programs

# Conversion programs

Settings → Conversions → Check features, or tray → Check software, shows Ready, Some features missing, Not installed, or Needs attention. Expand a group to see individual checks. Being installed alone does not make an engine Ready.

Choose the program yourself. For office exports the repository list contains LibreOffice Fresh and Still without a preferred selection. External programs must expose a supported conversion command interface; an ordinary viewer cannot automatically replace a batch conversion engine. Failed checks explain what was unavailable and keep the existing selection. Compatible selected engines are used for actual conversions, not just for opening files.

On Arch/CachyOS, opt into downloads for selected programs, review the package names, then press **Download and install**. Your selected terminal opens the system package installer, which shows dependencies/sizes and requests confirmation and authentication. The helper accepts only predefined package plans. It does not execute shell command text, run AUR scripts, bypass signatures, force dependency changes, refresh repositories, or upgrade the system. After completion Petal checks capabilities again. Closing first-launch setup discards draft preferences; explicitly approved package installations remain installed.

Other distributions, unavailable terminals, stale repositories, or unsupported programs use your normal software manager or the selected program's external download page. An installation failure is reported; no forced repair is attempted. Formatted Markdown → PDF may require a separate compatible PDF engine; installing Pandoc alone does not guarantee that route.
