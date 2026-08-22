"""Abuse-Ring Sentinel.

Defense-only fraud detection: identifies the same UPI ID, phone number, or
device fingerprint being reused across multiple merchants to commit fraud,
and produces explainable, bounded risk verdicts with honestly measured
precision, recall, and false-positive cost.

Architecture and design documents live in /docs. Build log in docs/what-broke.md.
"""

__version__ = "0.1.0"
