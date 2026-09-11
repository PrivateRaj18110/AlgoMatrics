"""monitoring.v1 receiver.

Independent of the ``raj_monitor`` agent protocol in ``app/services/agent_service.py``.
The two ingest paths share a database and nothing else: separate credentials,
separate tables, separate validation, separate semantics.
"""
