"""End-to-end lifecycle + permission + anonymity tests (spec section 7: mandatory in CI)."""
import json
import shutil
import tempfile
from datetime import timedelta

import pyotp
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from compliance.management.commands.seed_demo import tone
from compliance.models import AuditLog, PrivacyNotice, Terms
from organisations.models import Company, CompanyMember, Interpreter, Rater
from rating.models import AnonymousItem, RatingTask
from reports.models import CompanyReport
from rounds.models import Round
from submissions.models import Assignment

TMP = tempfile.mkdtemp()
PW = "Sup3r#Strong-pass"


def wav(name="x.wav"):
    return SimpleUploadedFile(name, tone(1), content_type="audio/wav")


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                                         "OPTIONS": {"location": TMP}},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
                   REQUIRE_2FA=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FullFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def login(self, email):
        c = APIClient()
        r = c.post("/api/auth/login/", {"email": email, "password": PW}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c.credentials(HTTP_AUTHORIZATION="Bearer " + r.json()["access"])
        return c

    def setUp(self):
        Terms.objects.create(version=1, body="terms")
        PrivacyNotice.objects.create(version=1, body="privacy")
        User.objects.create_superuser("admin@t.test", PW)
        self.admin = self.login("admin@t.test")
        self.companies = {}
        for name in ("Alpha", "Beta", "Gamma"):
            r = self.admin.post("/api/admin/companies/", {"name": name, "contact_email": f"{name.lower()}@t.test"}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            u = User.objects.get(email=f"{name.lower()}@t.test")
            u.set_password(PW)
            u.save()
            c = Company.objects.get(name=name)
            c.terms_version_accepted = 1
            c.save()
            self.companies[name] = self.login(u.email)
        for i in range(3):
            u = User.objects.create_user(f"rater{i}@t.test", PW, role="rater")
            Rater.objects.create(user=u, languages=["Urdu"], is_calibrated=True)

    # ---------------------------------------------------------------- helpers
    def make_round(self, deadline_days=7):
        r = self.admin.post("/api/admin/rounds/", {
            "name": "R1", "language": "Urdu", "deadline": (timezone.now() + timedelta(days=deadline_days)).isoformat(),
            "company_ids": [c.pk for c in Company.objects.all()], "min_raters_per_item": 2, "pairwise_per_item": 2}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["id"]
        # cannot open without recordings
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/open/").status_code, 400)
        for title in ("Rec 1", "Rec 2"):
            rr = self.admin.post(f"/api/admin/rounds/{rid}/recordings/", {"title": title, "file": wav()}, format="multipart")
            self.assertEqual(rr.status_code, 201, rr.content)
            rec = rr.json()
            for t, cat, w in (("Take one tablet", "dosage", 1), ("Beware of rash", "warning", 2)):
                k = self.admin.post(f"/api/admin/recordings/{rec['id']}/keypoints/", {"text": t, "category": cat, "weight": w}, format="json")
                self.assertEqual(k.status_code, 201, k.content)
        return rid

    def add_interpreters(self):
        for name, client in self.companies.items():
            for j in range(2):
                r = client.post("/api/company/interpreters/", {"full_name": f"{name} Person{j}", "email": f"{name.lower()}{j}@i.test"}, format="json")
                self.assertEqual(r.status_code, 201, r.content)

    def submit_all(self, rid, quality):
        """quality: dict company -> number of 'good' recordings. All interpreters record everything."""
        for a in Assignment.objects.filter(round_id=rid):
            c = APIClient()
            c.credentials(HTTP_X_ASSIGNMENT_TOKEN=a.token())
            info = c.get("/api/interpreter/assignment/").json()
            self.assertNotIn("key_points", json.dumps(info))
            for rec in info["recordings"]:
                r = c.post(f"/api/interpreter/recordings/{rec['id']}/take/", {"file": wav("take.wav")}, format="multipart")
                self.assertEqual(r.status_code, 201, r.content)
            r = c.post("/api/interpreter/assignment/submit/")
            self.assertEqual(r.status_code, 200, r.content)

    # ---------------------------------------------------------------- tests
    def test_full_lifecycle(self):
        rid = self.make_round()
        self.add_interpreters()
        r = self.admin.post(f"/api/admin/rounds/{rid}/open/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Assignment.objects.filter(round_id=rid).count(), 6)
        self.assertTrue(any("secure link" in m.body for m in mail.outbox))
        # invalid transition
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/open/").status_code, 400)
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/distribute/", {}, format="json").status_code, 400)

        # submit: can't submit without all takes
        a0 = Assignment.objects.filter(round_id=rid).first()
        c0 = APIClient()
        c0.credentials(HTTP_X_ASSIGNMENT_TOKEN=a0.token())
        self.assertEqual(c0.post("/api/interpreter/assignment/submit/").status_code, 400)

        # tracker + company progress
        t = self.admin.get(f"/api/admin/rounds/{rid}/submission-status/").json()
        self.assertEqual(len(t["companies"]), 3)
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/reminders/", {"all": True}, format="json").json()["sent"], 6)

        self.submit_all(rid, None)
        prog = self.companies["Alpha"].get(f"/api/company/rounds/{rid}/progress/").json()
        self.assertTrue(all(i["submitted"] for i in prog["interpreters"]))
        self.assertNotIn("score", json.dumps(prog).lower())

        # re-record after submit is blocked
        a = Assignment.objects.filter(round_id=rid).first()
        c = APIClient()
        c.credentials(HTTP_X_ASSIGNMENT_TOKEN=a.token())
        rec_id = a.round.recordings.first().id
        self.assertEqual(c.post(f"/api/interpreter/recordings/{rec_id}/take/", {"file": wav()}, format="multipart").status_code, 403)

        # close + distribute
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/close/").status_code, 200)
        dry = self.admin.post(f"/api/admin/rounds/{rid}/distribute/", {"dry_run": True}, format="json").json()
        self.assertEqual(dry["items"], 12)
        d = self.admin.post(f"/api/admin/rounds/{rid}/distribute/", {}, format="json")
        self.assertEqual(d.status_code, 200, d.content)
        self.assertEqual(d.json()["tasks"], 24)          # 12 items x 2 raters
        self.assertGreater(d.json()["pairs"], 0)
        self.assertEqual(Round.objects.get(pk=rid).status, "rating")
        # a closed round can't be reopened after rating started
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/open/", {"deadline": (timezone.now() + timedelta(days=3)).isoformat()}, format="json").status_code, 400)

        # ---- rater anonymity
        rater_user = User.objects.get(email="rater0@t.test")
        rc = self.login(rater_user.email)
        tasks = rc.get("/api/rater/tasks/").json()["tasks"]
        self.assertTrue(tasks)
        forbidden = ["Alpha", "Beta", "Gamma", "Person", "@i.test", "take.wav", "interpreter"]
        payloads = [json.dumps(tasks)]
        for tk in tasks:
            detail = rc.get(f"/api/rater/tasks/{tk['id']}/")
            self.assertEqual(detail.status_code, 200)
            body = detail.json()
            payloads.append(json.dumps(body))
            self.assertNotIn("weight", json.dumps(body["key_points"]))
            self.assertNotIn("admin_notes", json.dumps(body))
            self.assertTrue(body["interpretation_audio_url"].startswith("/api/media/"))
        for p in payloads:
            for word in forbidden:
                self.assertNotIn(word.lower(), p.lower())
        pairs = rc.get("/api/rater/pairs/").json()["pairs"]
        for pr in pairs:
            pd = json.dumps(rc.get(f"/api/rater/pairs/{pr['id']}/").json())
            for word in forbidden:
                self.assertNotIn(word.lower(), pd.lower())
        # the rater cannot open someone else's task
        other = RatingTask.objects.exclude(rater__user=rater_user).first()
        self.assertEqual(rc.get(f"/api/rater/tasks/{other.pk}/").status_code, 404)
        # media: signed URL works, tampered does not
        url = rc.get(f"/api/rater/tasks/{tasks[0]['id']}/").json()["source_audio_url"]
        self.assertEqual(APIClient().get(url).status_code, 200)
        self.assertEqual(APIClient().get(url[:-4] + "xxx/").status_code, 404)

        # ---- score everything: Alpha good, Beta middle, Gamma poor
        quality = {"Alpha": "full", "Beta": "partial", "Gamma": "lost"}
        for rater in Rater.objects.all():
            rc = self.login(rater.user.email)
            for tk in rc.get("/api/rater/tasks/").json()["tasks"]:
                task = RatingTask.objects.get(pk=tk["id"])
                company = task.anonymous_item.interpretation.assignment.interpreter.company.name
                detail = rc.get(f"/api/rater/tasks/{tk['id']}/").json()
                # completing early fails
                self.assertEqual(rc.post(f"/api/rater/tasks/{tk['id']}/complete/").status_code, 400)
                scores = [{"key_point": k["id"], "value": quality[company], "comment": "ok"} for k in detail["key_points"]]
                self.assertEqual(rc.patch(f"/api/rater/tasks/{tk['id']}/", {"scores": scores, "overall_comment": "fine"}, format="json").status_code, 200)
                self.assertEqual(rc.post(f"/api/rater/tasks/{tk['id']}/complete/").status_code, 200)
                self.assertEqual(rc.patch(f"/api/rater/tasks/{tk['id']}/", {"scores": scores}, format="json").status_code, 403)  # locked
            for pr in rc.get("/api/rater/pairs/").json()["pairs"]:
                self.assertEqual(rc.post(f"/api/rater/pairs/{pr['id']}/", {"winner": "a"}, format="json").status_code, 200)
        self.assertEqual(Round.objects.get(pk=rid).status, "review")   # auto-moved when all tasks complete

        # ---- admin scores + override
        sc = self.admin.get(f"/api/admin/rounds/{rid}/scores/").json()
        by_company = {}
        for it in sc["items"]:
            by_company.setdefault(it["company"], []).append(it["score"])
        self.assertEqual(set(by_company["Alpha"]), {100.0})
        self.assertEqual(set(by_company["Beta"]), {50.0})
        self.assertEqual(set(by_company["Gamma"]), {0.0})
        item_id = sc["items"][0]["id"]
        self.assertEqual(self.admin.post(f"/api/admin/items/{item_id}/override/", {"score": 80}, format="json").status_code, 400)  # reason needed
        self.assertEqual(self.admin.post(f"/api/admin/items/{item_id}/override/", {"score": 80, "reason": "audio glitch"}, format="json").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="score_override").exists())
        self.admin.post(f"/api/admin/items/{item_id}/override/", {"score": None}, format="json")

        # ---- reports
        g = self.admin.post(f"/api/admin/rounds/{rid}/reports/generate/")
        self.assertEqual(g.json()["generated"], 3)
        reps = self.admin.get(f"/api/admin/rounds/{rid}/reports/").json()
        self.assertEqual(self.companies["Alpha"].get("/api/company/reports/").json(), [])   # drafts invisible
        rep_alpha = next(x for x in reps if x["company"] == "Alpha")
        self.assertEqual(self.admin.post(f"/api/admin/reports/{rep_alpha['id']}/release/").status_code, 400)  # not approved
        for x in reps:
            self.admin.patch(f"/api/admin/reports/{x['id']}/", {"summary": "Well done."}, format="json")
            self.assertEqual(self.admin.post(f"/api/admin/reports/{x['id']}/approve/").status_code, 200)
        rel = self.admin.post(f"/api/admin/rounds/{rid}/reports/release-all/").json()
        self.assertEqual(rel["released"], 3)
        self.assertEqual(Round.objects.get(pk=rid).status, "released")
        self.assertTrue(any("report for" in m.subject for m in mail.outbox))

        a_rep = self.companies["Alpha"].get("/api/company/reports/").json()
        self.assertEqual(len(a_rep), 1)
        detail = self.companies["Alpha"].get(f"/api/company/reports/{a_rep[0]['id']}/").json()
        self.assertEqual(detail["rank"], 1)
        self.assertEqual(detail["companies_count"], 3)
        text = json.dumps(detail)
        for word in ("Beta", "Gamma", "Person", "@i.test", "Take one tablet", "rash"):
            self.assertNotIn(word, text)
        self.assertEqual(len(detail["data"]["peer_distribution"]), 3)
        pdf = self.companies["Alpha"].get(f"/api/company/reports/{a_rep[0]['id']}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(b"".join(pdf.streaming_content)[:4], b"%PDF")
        # Beta cannot read Alpha's report
        self.assertEqual(self.companies["Beta"].get(f"/api/company/reports/{a_rep[0]['id']}/").status_code, 404)
        self.assertEqual(self.companies["Beta"].get(f"/api/company/reports/{a_rep[0]['id']}/pdf/").status_code, 404)
        # released snapshot is frozen even if a score changes afterwards
        before = CompanyReport.objects.get(pk=a_rep[0]["id"]).data
        AnonymousItem.objects.filter(round_id=rid).update(override_score=1)
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/reports/generate/").status_code, 400)
        self.assertEqual(CompanyReport.objects.get(pk=a_rep[0]["id"]).data, before)

        # ---- export + audit
        x = self.admin.get(f"/api/admin/rounds/{rid}/export.xlsx")
        self.assertEqual(x.status_code, 200)
        self.assertEqual(x.content[:2], b"PK")
        self.assertTrue(AuditLog.objects.filter(action="export").exists())
        self.assertEqual(self.admin.get("/api/admin/export/all.xlsx").status_code, 200)

        # ---- erasure: no trace of name / email, scores intact
        interp = Interpreter.objects.get(email="alpha0@i.test")
        self.assertEqual(self.admin.post(f"/api/admin/interpreters/{interp.pk}/erase/", {}, format="json").status_code, 400)
        self.assertEqual(self.admin.post(f"/api/admin/interpreters/{interp.pk}/erase/", {"confirm": True}, format="json").status_code, 200)
        interp.refresh_from_db()
        self.assertEqual(interp.full_name, "Erased interpreter")
        self.assertFalse(Assignment.objects.get(interpreter=interp, round_id=rid).interpretations.exclude(audio_path="").exists())
        self.assertTrue(AuditLog.objects.filter(action="erasure").exists())

    def test_permissions_matrix(self):
        rid = self.make_round()
        self.add_interpreters()
        self.admin.post(f"/api/admin/rounds/{rid}/open/")
        alpha, beta = self.companies["Alpha"], self.companies["Beta"]
        # company users hit admin / rater / interpreter endpoints -> 403
        for path in ("/api/admin/companies/", f"/api/admin/rounds/{rid}/", f"/api/admin/rounds/{rid}/scores/",
                     "/api/admin/audit/", "/api/rater/tasks/", "/api/interpreter/assignment/", "/api/admin/export/all.xlsx"):
            self.assertIn(alpha.get(path).status_code, (401, 403), path)
        # nobody unauthenticated
        self.assertEqual(APIClient().get("/api/company/rounds/").status_code, 401)
        # company never sees the answer key, even through its own round endpoints
        rounds = alpha.get("/api/company/rounds/").json()
        self.assertNotIn("key_points", json.dumps(rounds))
        self.assertNotIn("Take one tablet", json.dumps(alpha.get(f"/api/company/rounds/{rid}/progress/").json()))
        # interpreters: scoped to their own company
        alpha_interp = Interpreter.objects.get(email="alpha0@i.test")
        self.assertEqual(beta.get(f"/api/company/interpreters/{alpha_interp.pk}/").status_code, 404)
        self.assertEqual(beta.patch(f"/api/company/interpreters/{alpha_interp.pk}/", {"full_name": "x"}, format="json").status_code, 404)
        ids = [i["id"] for i in beta.get("/api/company/interpreters/").json()]
        self.assertNotIn(alpha_interp.pk, ids)
        # a company cannot add an interpreter that duplicates an email in its own company
        self.assertEqual(alpha.post("/api/company/interpreters/", {"full_name": "Dup", "email": "alpha0@i.test"}, format="json").status_code, 400)
        # interpreter link only reaches its own assignment; recording ids from other rounds are 404
        a = Assignment.objects.filter(interpreter=alpha_interp).first()
        ic = APIClient()
        ic.credentials(HTTP_X_ASSIGNMENT_TOKEN=a.token())
        self.assertEqual(ic.get("/api/interpreter/assignment/").status_code, 200)
        self.assertEqual(ic.get("/api/admin/companies/").status_code, 403)
        self.assertEqual(ic.post("/api/interpreter/recordings/99999/take/", {"file": wav()}, format="multipart").status_code, 404)
        bad = APIClient()
        bad.credentials(HTTP_X_ASSIGNMENT_TOKEN="not-a-token")
        self.assertEqual(bad.get("/api/interpreter/assignment/").status_code, 401)
        # deadline: upload/submit -> 403
        Round.objects.filter(pk=rid).update(deadline=timezone.now() - timedelta(hours=1))
        rec_id = a.round.recordings.first().id
        r = ic.post(f"/api/interpreter/recordings/{rec_id}/take/", {"file": wav()}, format="multipart")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["code"], "deadline_passed")
        self.assertEqual(ic.post("/api/interpreter/assignment/submit/").status_code, 403)
        # per-interpreter extension makes it work again
        ext = self.admin.post(f"/api/admin/rounds/{rid}/extend/", {"deadline": (timezone.now() + timedelta(days=1)).isoformat(), "assignment_id": a.pk}, format="json")
        self.assertEqual(ext.status_code, 200, ext.content)
        self.assertEqual(ic.post(f"/api/interpreter/recordings/{rec_id}/take/", {"file": wav()}, format="multipart").status_code, 201)
        other = Assignment.objects.exclude(pk=a.pk).first()
        oc = APIClient()
        oc.credentials(HTTP_X_ASSIGNMENT_TOKEN=other.token())
        self.assertEqual(oc.post(f"/api/interpreter/recordings/{rec_id}/take/", {"file": wav()}, format="multipart").status_code, 403)

    def test_terms_block_and_reaccept(self):
        alpha = self.companies["Alpha"]
        self.assertEqual(alpha.get("/api/company/interpreters/").status_code, 200)
        Terms.objects.create(version=2, body="new terms")
        r = alpha.get("/api/company/interpreters/")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["code"], "terms_required")
        self.assertEqual(alpha.get("/api/company/terms/").status_code, 200)       # allowed before accepting
        self.assertEqual(alpha.post("/api/company/terms/accept/", {"version": 1}, format="json").status_code, 400)
        self.assertEqual(alpha.post("/api/company/terms/accept/", {"version": 2}, format="json").status_code, 200)
        self.assertEqual(alpha.get("/api/company/interpreters/").status_code, 200)
        self.assertEqual(Company.objects.get(name="Alpha").terms_version_accepted, 2)

    def test_round_open_needs_key_points_and_status_machine(self):
        r = self.admin.post("/api/admin/rounds/", {"name": "X", "language": "Urdu",
                            "deadline": (timezone.now() + timedelta(days=2)).isoformat(),
                            "company_ids": [Company.objects.first().pk]}, format="json").json()
        rid = r["id"]
        rr = self.admin.post(f"/api/admin/rounds/{rid}/recordings/", {"title": "T", "file": wav()}, format="multipart").json()
        res = self.admin.post(f"/api/admin/rounds/{rid}/open/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("key point", res.json()["message"])
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/close/").status_code, 400)       # draft -> closed illegal
        self.assertEqual(self.admin.post(f"/api/admin/rounds/{rid}/archive/").status_code, 400)
        self.assertEqual(self.admin.post("/api/admin/rounds/%d/open/" % rid).status_code, 400)

    def test_scoring_formula_and_rank_hiding(self):
        """Weighted formula and the <3 companies ranking rule."""
        from rating.models import ChecklistScore
        from reports.scoring import build_report_data, rank_companies
        rid = self.make_round()
        self.add_interpreters()
        Company.objects.filter(name="Gamma").update(status="inactive")
        rd = Round.objects.get(pk=rid)
        rd.participations.filter(company__name="Gamma").delete()
        self.admin.post(f"/api/admin/rounds/{rid}/open/")
        self.submit_all(rid, None)
        self.admin.post(f"/api/admin/rounds/{rid}/close/")
        self.admin.post(f"/api/admin/rounds/{rid}/distribute/", {"raters_per_item": 2}, format="json")
        # score one task: warning (w=2) full, dosage (w=1) lost -> 2/3*100
        task = RatingTask.objects.first()
        rec = task.anonymous_item.interpretation.source_recording
        for k in rec.key_points.all():
            ChecklistScore.objects.create(rating_task=task, key_point=k, value="full" if k.category == "warning" else "lost")
        from reports.scoring import task_score
        self.assertAlmostEqual(task_score(task), 200 / 3, places=4)
        # only two companies participate -> ranking hidden
        from reports.scoring import company_aggregates
        aggs = company_aggregates(rd)
        for a in aggs.values():
            a["score"] = a["score"] if a["score"] is not None else 50.0
        ranks, n = rank_companies(aggs)
        data = build_report_data(rd, Company.objects.get(name="Alpha"), aggs, ranks, n)
        self.assertFalse(data["ranking_visible"])
        self.assertEqual(data["peer_distribution"], [])
        self.assertIsNone(data["rank"])

    def test_auth_2fa_and_lockout(self):
        with override_settings(REQUIRE_2FA=True):
            c = APIClient()
            r = c.post("/api/auth/login/", {"email": "admin@t.test", "password": PW}, format="json").json()
            self.assertTrue(r["mfa_required"] and r["mfa_setup_required"])
            self.assertNotIn("access", r)
            setup = c.post("/api/auth/mfa/setup/", {"mfa_token": r["mfa_token"]}, format="json").json()
            self.assertEqual(len(setup["backup_codes"]), 10)
            self.assertEqual(c.post("/api/auth/mfa/verify/", {"mfa_token": r["mfa_token"], "code": "000000"}, format="json").status_code, 401)
            ok = c.post("/api/auth/mfa/verify/", {"mfa_token": r["mfa_token"], "code": pyotp.TOTP(setup["secret"]).now()}, format="json")
            self.assertEqual(ok.status_code, 200)
            self.assertIn("access", ok.json())
            self.assertIn("eqal_refresh", ok.cookies)
            # refresh via httpOnly cookie
            self.assertEqual(c.post("/api/auth/refresh/").status_code, 200)
            # second login now asks for a code but no setup
            r2 = APIClient().post("/api/auth/login/", {"email": "admin@t.test", "password": PW}, format="json").json()
            self.assertFalse(r2["mfa_setup_required"])
            # backup code works once
            bc = APIClient().post("/api/auth/mfa/verify/", {"mfa_token": r2["mfa_token"], "code": setup["backup_codes"][0]}, format="json")
            self.assertEqual(bc.status_code, 200)
            bc2 = APIClient().post("/api/auth/mfa/verify/", {"mfa_token": r2["mfa_token"], "code": setup["backup_codes"][0]}, format="json")
            self.assertEqual(bc2.status_code, 401)
        # lockout: 5 bad passwords
        u = User.objects.create_user("victim@t.test", PW, role="company")
        c = APIClient()
        for _ in range(5):
            self.assertEqual(c.post("/api/auth/login/", {"email": "victim@t.test", "password": "wrong"}, format="json").status_code, 401)
        locked = c.post("/api/auth/login/", {"email": "victim@t.test", "password": PW}, format="json")
        self.assertEqual(locked.status_code, 403)
        self.assertEqual(locked.json()["code"], "locked")

    def test_invite_accept_flow(self):
        mail.outbox.clear()
        r = self.admin.post("/api/admin/companies/", {"name": "Delta", "contact_email": "delta@t.test"}, format="json")
        link = [l for l in mail.outbox[-1].body.split() if "/invite/" in l][0]
        token = link.rsplit("/", 1)[1]
        c = APIClient()
        self.assertEqual(c.get(f"/api/auth/invite/{token}/").json()["email"], "delta@t.test")
        self.assertEqual(c.post("/api/auth/invite/accept/", {"token": token, "password": "short", "accept_terms": True}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/invite/accept/", {"token": token, "password": PW, "accept_terms": False}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/invite/accept/", {"token": token, "password": PW, "accept_terms": True}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/auth/invite/accept/", {"token": token, "password": PW, "accept_terms": True}, format="json").status_code, 400)  # single use
        self.assertEqual(Company.objects.get(name="Delta").terms_version_accepted, 1)
        self.assertEqual(self.login("delta@t.test") is not None, True)
