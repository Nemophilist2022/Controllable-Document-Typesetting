"""Ingestion layer.

Loads a thesis manuscript (.docx/.doc/.txt/.md/.tex) into a normalised
``DocumentModel`` and a template (YAML or natural language) into a
``RuleSet``. All upper layers must access the document through
``DocumentModel`` and never directly through ``python-docx``.
"""
