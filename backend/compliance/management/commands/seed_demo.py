import io
from datetime import timedelta
import math
import struct
import wave

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from compliance.models import PrivacyNotice, SiteSettings, Terms
from config.storage import new_path
from organisations.models import Company, CompanyMember, Interpreter, Rater
from rating.models import PracticeItem, PracticeKeyPoint
from rounds.models import KeyPoint, Round, RoundParticipation, SourceRecording

PASSWORD = "Demo#Pass2026!"
ADMIN_EMAIL = "admin@eqal.test"

TERMS = """# EQAL participation terms (v1)

By taking part in an EQAL round your company agrees that:

1. Interpretations are recorded for quality assessment only.
2. Recordings are scored anonymously by independent raters.
3. Your company receives a private report; peers are shown anonymously and individual interpreters are never identified.
4. Audio is deleted after the retention period stated on the round.
"""
PRIVACY = """# Privacy notice

**What we collect:** interpreter name, email and the audio of their interpretations (personal data under UK GDPR).
**Why:** to assess interpreter quality in scripted rounds. Lawful basis: legitimate interests / contract.
**How long:** audio is deleted after the round's retention period; anonymised aggregate scores are kept.
**Who sees it:** raters hear audio without any identity; companies only see their own aggregate report.
**Sub-processors:** hosting provider (UK/EU), transactional email provider (EU).
**Your rights:** access, rectification, erasure. Contact: privacy@eqal.example
"""


def tone(seconds=3, freq=440):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / 16000)
                                                * (0.5 + 0.5 * math.sin(i / 2000))))
                          for i in range(16000 * seconds))
        w.writeframes(frames)
    return buf.getvalue()


def save_tone(folder, freq):
    return default_storage.save(new_path(folder, ".wav"), ContentFile(tone(3, freq)))


class Command(BaseCommand):
    help = "Create demo data (admin, 3 companies, interpreters, raters, a draft round, a practice item)."

    def handle(self, *args, **opts):
        SiteSettings.get()
        if not Terms.latest():
            Terms.objects.create(version=1, body=TERMS)
        if not PrivacyNotice.latest():
            PrivacyNotice.objects.create(version=1, body=PRIVACY)
        if not User.objects.filter(email=ADMIN_EMAIL).exists():
            User.objects.create_superuser(ADMIN_EMAIL, PASSWORD)
        companies = []
        for i, name in enumerate(["Alpha Language Services", "Beta Interpreting", "Gamma Linguists"]):
            c, _ = Company.objects.get_or_create(name=name, defaults={
                "contact_email": f"contact@{name.split()[0].lower()}.test", "terms_version_accepted": 1,
                "terms_accepted_at": timezone.now()})
            email = f"company{i + 1}@eqal.test"
            if not User.objects.filter(email=email).exists():
                u = User.objects.create_user(email, PASSWORD, role="company")
                CompanyMember.objects.create(user=u, company=c)
            for j in range(3):
                Interpreter.objects.get_or_create(company=c, email=f"interp{i + 1}{j + 1}@{name.split()[0].lower()}.test",
                                                  defaults={"full_name": f"{name.split()[0]} Interpreter {j + 1}"})
            companies.append(c)
        for i in range(3):
            email = f"rater{i + 1}@eqal.test"
            if not User.objects.filter(email=email).exists():
                u = User.objects.create_user(email, PASSWORD, role="rater")
                Rater.objects.create(user=u, languages=["Urdu", "Punjabi"], is_calibrated=True)
        if not Round.objects.exists():
            r = Round.objects.create(name="Urdu Pilot Round", language="Urdu",
                                     deadline=timezone.now() + timedelta(days=14), min_raters_per_item=2,
                                     pairwise_per_item=2, retention_days=90)
            for c in companies:
                RoundParticipation.objects.create(round=r, company=c)
            scripts = [("GP consultation: chest pain", ["Chest pain started two days ago", "Take one tablet twice a day",
                                                         "Seek urgent help if breathless", "Do you have any allergies?"]),
                       ("Pharmacy: new prescription", ["Take with food", "Do not drink alcohol", "Course lasts seven days"])]
            for n, (title, points) in enumerate(scripts):
                rec = SourceRecording.objects.create(round=r, title=title, order=n, audio_path=save_tone("source", 330 + 110 * n),
                                                     mime_type="audio/wav", duration_sec=3,
                                                     transcript=f"[Scripted] {title}")
                cats = ["warning", "dosage", "warning", "doubt"]
                for k, text in enumerate(points):
                    KeyPoint.objects.create(source_recording=rec, order=k, text=text, category=cats[k % 4],
                                            weight=2 if cats[k % 4] == "warning" else 1)
        if not PracticeItem.objects.exists():
            p = PracticeItem.objects.create(title="Practice 1: allergy question", language="Urdu",
                                            source_audio_path=save_tone("practice", 392),
                                            interpretation_audio_path=save_tone("practice", 294))
            for k, (text, ref, why) in enumerate([("Asks about allergies", "full", "Fully conveyed."),
                                                  ("Dosage: twice a day", "partial", "Frequency given but not the duration."),
                                                  ("Warning: stop if rash appears", "lost", "Omitted entirely.")]):
                PracticeKeyPoint.objects.create(item=p, order=k, text=text, reference_value=ref, explanation=why)
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  admin   {ADMIN_EMAIL} / {PASSWORD}")
        self.stdout.write(f"  company company1@eqal.test .. company3@eqal.test / {PASSWORD}")
        self.stdout.write(f"  rater   rater1@eqal.test .. rater3@eqal.test / {PASSWORD}")
        self.stdout.write("  Admin and rater logins need 2FA (scan the QR on first login).")
