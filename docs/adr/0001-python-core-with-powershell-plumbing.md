# ADR 0001: Python core, thin PowerShell plumbing layer

## Status
Accepted.

## Context
The tool must run on Windows 11 but is developed on a Linux box. It needs to
identify file types from magic bytes, metadata (EXIF, PE version info, ISO
labels, etc.), and Zone.Identifier alternate data streams, then be testable
without a Windows machine in the loop.

Options considered:
- **PowerShell only.** Native on Windows, trivial Scheduled Task registration
  and ADS access, but weak libraries for parsing file formats (PE headers,
  EXIF, PDF metadata, fonts) and much harder to unit test on Linux.
- **Python core + thin PowerShell layer.** Python has mature libraries for
  every extractor in PLAN.md section 4.2, runs identically on both OSes via
  `uv`, and can read Zone.Identifier streams itself
  (`open(path + ":Zone.Identifier")`) — no PowerShell needed for that part.

## Decision
Python is the core (CLI, identification, routing, gating, apply, journal).
PowerShell is used only for Windows-specific plumbing that has no good Python
equivalent: registering the weekly Scheduled Task, an optional toast
notification, and an install script (`scripts/windows/`).

## Consequences
- Windows-only behavior (ADS, file locks, Task Scheduler) sits behind small
  adapters with Linux no-op/fake implementations, so the bulk of the codebase
  is testable on the Linux dev box.
- CI runs an `ubuntu-latest` + `windows-latest` matrix; only the PowerShell
  scripts and the Windows-specific adapters need manual verification on the
  real PC.
- Adds a dependency on `uv` being installed on Windows, which `install.ps1`
  (M4) is responsible for bootstrapping.
