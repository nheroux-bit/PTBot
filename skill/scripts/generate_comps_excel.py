#!/usr/bin/env python3
"""Compatibility wrapper exposing PTBot's Excel generator."""

from _bootstrap import ensure_ptbot_importable

ensure_ptbot_importable()

from ptbot.excel import (
    generate_comps_excel,
    generate_comps_excel_from_deals,
)

__all__ = ["generate_comps_excel", "generate_comps_excel_from_deals"]
