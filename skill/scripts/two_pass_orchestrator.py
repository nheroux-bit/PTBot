#!/usr/bin/env python3
"""Compatibility wrapper exposing PTBot's two-pass orchestrator."""

from _bootstrap import ensure_ptbot_importable

ensure_ptbot_importable()

from ptbot.orchestrator import run_pipeline

__all__ = ["run_pipeline"]
