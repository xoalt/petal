# Security

Report vulnerabilities through this repository's private GitHub security advisory reporting when available. Otherwise contact the maintainer through their GitHub profile before sharing an exploit. Do not put confidential documents, personal paths, credentials, or private media in public issues.

Conversions are local. Optional system package installation is a separate user-approved action using the distribution package manager. Petal does not receive administrator privileges; its package helper requests authentication only for the selected package-manager transaction. No passwords are collected by Petal.

Converters and parsers process complex, potentially hostile formats. Keep your distribution's conversion programs current. Petal uses argument arrays rather than shell interpolation, protects existing output names, stages conversions, and validates archive members. These defenses and sample tests do not guarantee safety for every malformed file.

The vendored pypdf version is pinned in requirements-audit.txt and checked in CI. Host libraries and conversion engines are supplied by the distribution; they are outside the vendored dependency scan. Use your distribution's security updates for those programs.
