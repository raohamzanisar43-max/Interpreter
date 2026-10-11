# EQAL — Quick start guide

## 1. Install once (Windows)
- **Python 3.12** (python.org — tick "Add Python to PATH")
- **Node.js 20+** (nodejs.org)
- Internet is needed on the first run only.

## 2. Start
1. Unzip the folder, e.g. to `C:\EQAL`.
2. Open PowerShell in that folder (Shift + right-click → "Open PowerShell window here").
3. Run:
   ```
   powershell -ExecutionPolicy Bypass -File .\start.ps1
   ```
   The first run takes a few minutes (installs everything, creates demo data). Wait for
   `EQAL running at http://127.0.0.1:8811`, then open that address in Chrome/Edge. Keep the window open.
   - Port busy? add `-Port 8900`. Want to skip 2FA for a quick look? add `-No2FA`.
   - To stop: Ctrl+C. To start again later, run the same command.

## 3. Logins (password for all: `Demo#Pass2026!`)
| Who | Email | Notes |
|---|---|---|
| Admin | admin@eqal.test | needs 2FA (see below) |
| Rater | rater1@eqal.test, rater2@…, rater3@… | needs 2FA |
| Company | company1@eqal.test, company2@…, company3@… | no 2FA |

**2FA, first login:** scan the QR with Google/Microsoft Authenticator, click *Download codes*, type the
6-digit code from the app, *Confirm*. (Backup codes are only for later logins if you lose the phone — not for this step.)
No phone? In a second PowerShell window run
`backend\.venv\Scripts\python.exe backend\manage.py totp admin@eqal.test` for the current code.
5 wrong passwords/codes lock the account for 15 minutes.

## 4. Walk through the whole process
1. **Admin → Rounds → "Urdu Pilot Round" → Open round.** Interpreters are created and invited.
2. **Admin → Settings → Sent emails.** Open an "EQAL: please record…" email and copy its `/i/…` link.
3. **Interpreter:** open that link (new tab or phone) → Start → mic test → Record each item → *Keep* →
   Review & submit. (Allow the microphone. You can also *Upload audio file*.) Repeat with other links or just one.
4. **Admin → round → Close round → Distribution → Preview load → Distribute.**
5. **Rater:** sign in as `rater1…3` → *Practice* (score the sample, see feedback) → *Scoring tasks* → listen to
   Original + Interpretation, press `1` Fully / `2` Partly / `3` Lost, `Space` play/pause → *Mark complete*.
   Also do *Compare two*. Repeat for each rater (or Admin → Scores → *Move to Review* with force).
6. **Admin → round → Scores:** check flagged disagreements, click an item to see each rater, override a score
   (reason required). Then **Reports → Generate → Preview → Approve → Release all approved.**
7. **Company:** sign in as `company1…3` → *Reports* (score, rank, anonymous peers, Download PDF) and
   *History & trend*. Companies never see answer keys, other company names or individual interpreters.

## 5. Other admin screens
Companies / Raters (add + invite), Rater quality, Practice items, Exports (Excel), Audit log (CSV),
Data protection (export, delete audio, erase an interpreter), Settings (retention, reminders, terms, privacy, email texts).

## 6. Problems
- *"Account locked"* → wait 15 min, or ask the person who set this up.
- *Page not loading* → check the PowerShell window is still running.
- *Start again from scratch* → `.\start.ps1 -Reset` (deletes demo data and starts fresh).
