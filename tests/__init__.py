"""Offline test suite for Headlinne.

These tests never touch the network or the Gemini/Buffer APIs. They cover
the deterministic logic that guarantees the brief's hard rules: forbidden
punctuation is stripped, character limits hold, the schedule maths is correct,
ranking clusters and scores stories sensibly, and de-duplication works.

Run them either way:

    python -m tests          # zero-dependency runner, no pytest needed
    pytest tests             # if you have pytest installed
"""
