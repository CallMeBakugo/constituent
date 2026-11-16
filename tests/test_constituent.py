import copy
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from constituent.advocacy import ensure_templates, letter, mailto
from constituent.sources import lifecycle
from constituent.store import Store


class StoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.store = Store(cls.root / "local.sqlite")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_default_hubs_and_court_cache(self):
        hubs = self.store.hubs()
        for hub in hubs[:3]:
            self.assertTrue(self.store.bills(hub["phrases"]))
        self.assertTrue(self.store.get_setting("court_filings"))
        chat = hubs[0]
        result = self.store.bills(chat["phrases"], "HR 7757")
        self.assertEqual([bill["bill_id"] for bill in result], ["H.R. 7757"])

    def test_new_action_alert_is_persistent_and_idempotent(self):
        bill = copy.deepcopy(self.store.bills("Farm Freedom to Repair Act")[0])
        action = {"date": "2026-11-15", "text": "Test only", "code": "", "links": []}
        bill["actions"].insert(0, action)
        with self.store.connect() as db:
            self.assertEqual(self.store.write_bills(db, [bill], notify=True), 1)
        self.assertTrue(self.store.bills("Farm Freedom to Repair Act")[0]["unread"])
        with self.store.connect() as db:
            self.assertEqual(self.store.write_bills(db, [bill], notify=True), 0)
        self.store.mark_read(bill["key"])
        self.assertFalse(self.store.bills("Farm Freedom to Repair Act")[0]["unread"])

    def test_local_district_resolution_and_letter(self):
        profile = {"name": "Example Person", "address": "123 Test Street\nTest City", "state": "TN", "district": "05"}
        offices = self.store.representatives(profile)
        self.assertEqual({member["chamber"] for member in offices}, {"House", "Senate"})
        self.assertEqual(len(offices), 3)
        self.assertTrue(all(office["phone"] and (office["form"] or office["site"]) for office in offices))
        bill = self.store.bills("Kids Online Safety Act", "S 1748")[0]
        subject, body = letter(ensure_templates(self.root), bill, offices[0], profile, "oppose")
        self.assertIn("[Oppose] S. 1748", subject)
        self.assertIn(profile["address"], body)
        url = urlsplit(mailto("test@example.com", subject, body))
        self.assertEqual(url.path, "test@example.com")
        self.assertEqual(parse_qs(url.query)["body"][0], "\r\n".join(body.splitlines()))
        entry = self.store.log(bill["bill_id"], offices[0]["name"], "oppose", "Copied")
        self.store.mark_sent(entry)
        self.assertEqual(self.store.diary()[0]["status"], "Marked sent")
        self.assertNotIn(profile["address"], repr(dict(self.store.diary()[0])))

    def test_procedural_failure_is_distinct_from_bill_failure(self):
        action = {"code": "H1L220", "text": "Rule H. Res. 1175 failed passage of House."}
        referral = {"code": "H11100", "text": "Referred to the Committee on the Judiciary."}
        failure = {"code": "", "text": "On passage Failed by recorded vote."}
        self.assertEqual(lifecycle([action, referral], [], "HR"), "In Committee")
        self.assertEqual(lifecycle([failure, referral], [], "HR"), "Failed")
        self.assertEqual(lifecycle([failure, referral], ["119-1"], "HR"), "Enacted")


if __name__ == "__main__":
    unittest.main()
