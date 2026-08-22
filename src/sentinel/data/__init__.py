"""Synthetic data generation for Abuse-Ring Sentinel.

Produces the 900 clean / 100 fraud evaluation dataset specified in
docs/04-data-design.md: a realistic clean population plus injected fraud
rings, ring-stratified 60/20/20 splits with an identity-leakage guard, and
strict separation between serving-shaped events and evaluation labels.
"""
