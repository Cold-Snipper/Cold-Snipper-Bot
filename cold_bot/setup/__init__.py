"""
Setup phases for configuring Cold Bot.

This package currently provides:
- phase1: source selection (websites / facebook / both)
- phase2: source-specific parameter collection

Each phase is designed to be callable independently so we can
unit-test them and run them from a CLI orchestrator.
"""

