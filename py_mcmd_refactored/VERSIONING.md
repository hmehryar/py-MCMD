# py-MCMD Versioning Strategy

py-MCMD uses **Semantic Versioning** with a Python-friendly version string format.

## Version format

Stable releases use:

`MAJOR.MINOR.PATCH`

Examples:

- `0.1.0`
- `0.2.3`
- `1.0.0`

Pre-release and development versions use PEP 440-compatible suffixes:

- Development snapshot: `MAJOR.MINOR.PATCH.devN`
- Release candidate: `MAJOR.MINOR.PATCHrcN`

Examples:

- `0.2.0.dev1`
- `0.2.0rc1`

## Meaning of version components

### MAJOR
Increment the major version for breaking changes, including changes such as:

- incompatible CLI behavior
- incompatible configuration/JSON behavior
- incompatible restart behavior
- incompatible output or logging conventions that users/scripts depend on

### MINOR
Increment the minor version for backward-compatible feature additions, including:

- new framework capabilities
- new optional configuration fields
- new supported workflows
- new user-facing functionality that does not break existing usage

### PATCH
Increment the patch version for backward-compatible fixes and small improvements, including:

- bug fixes
- correctness fixes
- non-breaking refactors
- documentation or test corrections tied to an existing release line

## Initial version for the refactored framework

The refactored py-MCMD framework starts at:

`2.0.0`

- FIFO implementation version

`2.1.0`

This indicates an early but usable release of the refactored architecture.

## Project policy

- py-MCMD must have one authoritative version string in the codebase.
- Other locations must read from that single source of truth.
- Version strings must not be duplicated manually across multiple code files.
- User-facing version output must always come from the same authoritative version source.

