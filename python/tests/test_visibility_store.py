from __future__ import annotations

import unittest

from agentic_readiness.visibility_store import VisibilityStore


class VisibilityStoreTests(unittest.TestCase):
    def test_store_disabled_without_database_url(self) -> None:
        store = VisibilityStore("")
        self.assertFalse(store.enabled)
        self.assertIsNone(store.insert_run({"job_id": "j1"}))
        self.assertEqual(store.list_runs(), [])

    def test_insert_helpers_are_noop_when_disabled(self) -> None:
        store = VisibilityStore("")
        store.insert_provider_metrics(0, {})
        store.insert_topics(0, [])
        store.insert_probes(0, [])
        self.assertEqual(store.list_runs(url="https://example.com"), [])


if __name__ == "__main__":
    unittest.main()
