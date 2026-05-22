"""PDF 商標替換工具 backend package.

Phase 1 (input + preview skeleton): FastAPI service that ingests one vector PDF,
preserves the original immutably under a three-directory layout, and serves each
page rendered to PNG by PyMuPDF at a known DPI plus the page metadata that Phase 2's
coordinate mapper consumes.
"""
