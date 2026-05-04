# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- COST-ESTIMATE.md with pre-build cost analysis and recorded build decision
- PROJECT-DEFINITION.vbrief.json with project identity, tech stack, and architecture

### Changed
- Migrated to vBRIEF-centric document model: SPECIFICATION.md and PROJECT.md replaced with deprecated-redirect stubs
- Moved build scope vBRIEF from proposed/ to completed/
- Updated all specification.vbrief.json task statuses from pending to completed
- Fixed mypy type errors in excel.py: added Worksheet/Cell annotations, narrowed union types for implied_metric
- Applied black formatting to excel.py and test_outputs.py
- Sorted imports with isort in excel.py

### Fixed
- excel.py: implied_metric division guard now uses explicit None check instead of `in (None, 0)` to satisfy mypy
- excel.py: write_deal_row narrows dict values through isinstance before passing to implied_metric
