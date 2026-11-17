# Basketball Teams

A full-stack basketball team manager built with Flask. It provides a public team page, a single password-protected admin workspace, publish-only history snapshots, and a versioned JSON API.

## Version 1.0.0 features

- Public current-team page and public historical snapshots.
- Admin-only player management and API-key controls.
- Manual assignments, configurable team names, randomization and unlimited rerolls.
- Drafts remain private until explicitly published.
- Every publication creates a permanent history entry.
- API keys are stored as SHA-256 hashes and shown only once.
- API write access publishes a new snapshot, just like the website.

## Local setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
flask --app app create-admin
flask --app app run
```

Open http://127.0.0.1:5000. The SQLite database is created automatically in `instance/basketball.sqlite3`.

## First-time admin setup

Run `flask --app app create-admin` once and follow the prompts. Create the single administrator before deploying or sharing the site. Open `/manage` to enter the admin area: it redirects to `/manage/login` when signed out and to `/manage/dashboard` when authenticated. The homepage deliberately contains no link to the admin area. All `/manage` routes except the login page require the administrator session. The dashboard links to the editor, API-key controls, publication history and sign-out.

## PythonAnywhere deployment

1. Create a **Python 3.10+** web app using the manual Flask configuration.
2. Clone this repository into your PythonAnywhere home directory.
3. Create and activate a virtual environment, then install `requirements.txt`.
4. In the Web tab, set the source directory to the repository folder and the WSGI file to import `application` from `wsgi.py`.
5. Set the virtualenv path to your environment.
6. In the WSGI configuration file, ensure the project directory is on `sys.path` and set a strong secret key before importing the app:

```python
import os, sys
project = '/home/YOUR_USERNAME/basketball-teams'
if project not in sys.path:
    sys.path.insert(0, project)
os.environ['SECRET_KEY'] = 'PASTE-A-LONG-RANDOM-SECRET-HERE'
os.environ['DATABASE_PATH'] = '/home/YOUR_USERNAME/basketball-teams/instance/basketball.sqlite3'
os.environ['COOKIE_SECURE'] = '1'
from app import app as application
```

7. In a PythonAnywhere Bash console, activate the same virtualenv and run `flask --app app create-admin`.
8. Reload the web app from the Web tab.

Keep the database in a persistent directory outside temporary deployment/build folders. Back it up regularly. Do not commit the database, passwords, API keys, or secret key.

## REST API

All endpoints are under `/api/v1/`.

| Method | Endpoint | Access |
| --- | --- | --- |
| GET | `/api/v1/teams` | Public |
| PUT | `/api/v1/teams` | API key |
| GET | `/api/v1/teams/<history_id>` | Public historical snapshot by ID |
| GET | `/api/v1/teams/<yyyymmdd>` | Latest snapshot published on that date |
| GET | `/api/v1/players` | Public active players |

Example update request:

```json
{
  "note": "Friday game",
  "teams": {
    "Blue": ["Player One", "Player Two"],
    "Red": ["Player Three", "Player Four"]
  }
}
```

```bash
curl -X PUT "https://YOUR-SITE.pythonanywhere.com/api/v1/teams" \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"note":"Friday game","teams":{"Blue":["Player One"],"Red":["Player Two"]}}'
```

The API accepts player names that already exist and are active in the roster. Every player may appear at most once. An API update publishes immediately and creates a history snapshot.

## Security notes

- Passwords use Werkzeug's secure password hashing.
- Every `/manage` route requires the single administrator session.
- POST forms use session-bound CSRF tokens.
- API keys are never stored in plaintext.
- Use HTTPS, a strong random `SECRET_KEY`, and secure deployment settings in production.
- Set `COOKIE_SECURE=1` when the site is served exclusively over HTTPS.
- The application has no friend accounts or public sign-in. The administrator password is set through the CLI during initial setup. Historical snapshots can be loaded into a draft and republished as a new snapshot.

## License

This project is licensed under the [MIT License](LICENSE).

## Version 2.0.0

Interactive friend profiles (display name, availability, and related profile controls) are intentionally out of scope for v1.0.0.
