import pyotp
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "DEV ONLY: print the current 2FA code for a user (saves reaching for a phone while testing)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("Only available when EQAL_DEBUG=1.")
        u = User.objects.filter(email=opts["email"]).first()
        if not u or not u.totp_secret:
            raise CommandError("User not found or 2FA not set up yet (open the setup screen first).")
        self.stdout.write(pyotp.TOTP(u.totp_secret).now())
