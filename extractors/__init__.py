"""RPI_Cluster extractors package.

Each module exposes a single entry point::

    def extract(molecules: list[dict], config: dict) -> list[dict]

returning raw dicts (field names matching the canonical schema where possible).
All normalization — status mapping, date parsing, null fill — is performed later
by ``normalize.py``; extractors stay focused on retrieval only.
"""
