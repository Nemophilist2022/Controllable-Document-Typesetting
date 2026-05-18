"""Orchestrator layer.

The harness main loop: plan → act → evaluate → diagnose → policies gate
→ replan. Owns snapshots, rollback, retries and human-in-the-loop gates.
"""
