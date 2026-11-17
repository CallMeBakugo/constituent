import copy
import io
import tempfile
import unittest
from pathlib import Path
from datetime import date
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

from constituent.advocacy import ensure_templates, letter, mailto
from constituent.agency import comment_window
from constituent.legislation import bill_stage
from constituent.office_data import contact_link, office_vote, roll_xml, vote_records
from constituent.sources import lifecycle
from constituent.store import Store
from constituent.sync import current_congress


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

    def test_hub_matches_official_text_across_versions(self):
        package = "BILLS-119hr7757rfs"
        key = "119-hr-7757"

        def archive_for(passage, version=package, published="2026-05-06"):
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as archive:
                archive.writestr(
                    f"{version}.xml",
                    '<bill xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    f"<metadata><dublinCore><dc:date>{published}</dc:date></dublinCore>"
                    "exclude this metadata</metadata>"
                    f"<legis-body><text>{passage}</text></legis-body></bill>",
                )
            return buffer.getvalue()

        raw = archive_for("An otherwise unindexed passage about encrypted consultations.")
        with self.store.connect() as db:
            self.store.write_bill_text(db, raw)
            self.store.write_bill_text(db, raw)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM bill_text_versions WHERE bill_key=?", (key,)
            ).fetchone()[0], 1)

        # The hub phrase and the requested title can match different index fields.
        matches = self.store.bills("encrypted consultations", "HR 7757")
        self.assertEqual([bill["key"] for bill in matches], [key])
        snippet = self.store.text_match(key, "encrypted consultations")
        self.assertEqual(snippet[0], package)
        self.assertIn("encrypted consultations", snippet[1])
        self.assertEqual(self.store.bills("exclude this metadata"), [])
        self.assertEqual(snippet[3:], ("2026-05-06", True))

        with self.store.connect() as db:
            self.store.write_bill_text(db, archive_for("The most recent version.", "BILLS-119hr7757eas", "2026-06-01"))
        self.assertEqual(self.store.text_match(key, "encrypted consultations")[3:], ("2026-05-06", False))
        self.assertEqual(self.store.bills("encrypted consultations", latest_only=True), [])
        self.assertIsNone(self.store.text_match(key, "encrypted consultations", latest_only=True))
        self.assertEqual([b["key"] for b in self.store.bills("most recent version", "HR 7757", latest_only=True)], [key])

        with self.store.connect() as db:
            self.store.write_bill_text(db, archive_for("A corrected passage about closed sessions."))
            corrected = self.store.bills("closed sessions", "HR 7757", db=db)
            self.assertEqual([bill["key"] for bill in corrected], [key])
            self.assertEqual(self.store.bills("encrypted consultations", db=db), [])

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

    def test_watch_outside_hubs_and_restart(self):
        store = self.store
        bill = copy.deepcopy(store.get_bill("119-hr-1"))
        store.set_watched(bill["key"], True)
        bill["actions"].insert(0, {"date": "2026-11-16", "text": "Watched test action", "code": "", "links": []})
        with store.connect() as db:
            self.assertEqual(store.write_bills(db, [bill], notify=True), 1)
        reopened = Store(store.path)
        self.assertTrue(reopened.is_watched(bill["key"]))
        self.assertEqual(reopened.recent_activity()[0]["text"], "Watched test action")
        with reopened.connect() as db:
            self.assertEqual(reopened.write_bills(db, [bill], notify=True), 0)
        reopened.set_watched(bill["key"], False)

    def test_calendar_and_procedural_defeat(self):
        actions = [{"code": "", "text": "Read the second time. Placed on Senate Legislative Calendar under General Orders."}]
        stage = bill_stage(actions, "S")
        self.assertEqual((stage.label, stage.chamber), ("On Senate calendar", "Senate"))
        result = bill_stage([
            {"code": "", "text": "Motion to proceed to consideration of the House message rejected in Senate."},
            {"code": "8000", "text": "Passed/agreed to in House, as amended."},
            {"code": "17000", "text": "Passed Senate."},
        ], "S")
        self.assertEqual(result.label, "Passed House · Senate motion blocked")
        self.assertEqual(result.chamber, "Senate")
        stage = bill_stage([
            {"code": "", "text": "Received in the Senate and read twice and referred to the Committee on Commerce."},
            {"code": "8000", "text": "Passed/agreed to in House."},
        ], "HR")
        self.assertEqual(stage.label, "Passed House · In Senate committee")

    def test_congress_rollover_and_public_comment_window(self):
        self.assertEqual(current_congress(date(2027, 1, 2)), 119)
        self.assertEqual(current_congress(date(2027, 1, 3)), 120)
        self.assertEqual(comment_window(date(2026, 11, 16))[1], "2026-12-07")
        self.assertEqual(comment_window(date(2026, 12, 8))[1], "2027-02-22")
        self.assertIsNone(comment_window(date(2027, 3, 23)))

    def test_contact_and_vote_join_use_official_sources(self):
        site = "https://example.house.gov/"
        links = (
            b'<a href="https://unrelated.house.gov/contact">Email me</a>'
            b'<a href="/contact">Contact</a><a href="/contact/email-me">Email me</a>'
        )
        self.assertEqual(contact_link(links, site), "https://example.house.gov/contact/email-me")
        self.assertEqual(roll_xml("https://clerk.house.gov/Votes/2026228"),
                         ("https://clerk.house.gov/evs/2026/roll228.xml", "House"))
        self.assertIsNone(roll_xml("https://evil.example/evs/2026/roll228.xml"))
        data = (b'<rollcall-vote><vote-data><recorded-vote>'
                b'<legislator name-id="X000001"/><vote>Yea</vote>'
                b'</recorded-vote></vote-data></rollcall-vote>')
        self.assertEqual(office_vote({"id": "X000001", "chamber": "House"}, vote_records(data, "House")), "Yea")

    def test_senate_roll_join_disambiguates_shared_surnames(self):
        url = "https://www.senate.gov/legislative/LIS/roll_call_votes/vote1192/vote_119_2_00164.htm"
        self.assertEqual(roll_xml(url), (url.removesuffix(".htm") + ".xml", "Senate"))
        data = b"""<roll_call_vote><members>
        <member><last_name>Scott</last_name><first_name>Tim</first_name><state>SC</state><vote_cast>Yea</vote_cast></member>
        <member><last_name>Scott</last_name><first_name>Rick</first_name><state>FL</state><vote_cast>Nay</vote_cast></member>
        </members></roll_call_vote>"""
        records = vote_records(data, "Senate")
        office = {"name": "Tim Scott", "state": "SC", "chamber": "Senate"}
        self.assertEqual(office_vote(office, records), "Yea")
        self.assertEqual(office_vote(dict(office, state="TN"), records), "")

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
