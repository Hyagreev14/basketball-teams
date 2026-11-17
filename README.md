# Basketball Teams

A lightweight basketball team management website for organizing players, publishing team assignments, and keeping a history of previous teams.

Built with **Python and Flask**. The project is currently in development.

## Planned features

### Team management
- View the currently published teams on a public homepage.
- Manually assign players to teams and move players between teams.
- Optionally generate balanced teams by shuffling all registered players, regardless of their current team.
- Reroll randomized teams as many times as needed, then make manual adjustments.
- Keep changes as a draft until an administrator publishes them.

### Accounts
- Individual accounts for friends.
- **Version 1.0.0:** friends can sign in, view current and historical teams, and change their own password. Accounts are view-only.
- Administrators can create, disable, and reset accounts.
- **Version 2.0.0:** planned player profile features, such as display-name and availability management.

### Team history
- Save a snapshot whenever an administrator publishes teams.
- Browse previous team assignments.
- Keep published history immutable. Restoring an older arrangement creates a new publication rather than rewriting the past.

### REST API
A versioned API will allow approved API-key holders to read and update the same team data used by the website.

Planned endpoints include:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/teams` | Get the current teams |
| `PUT` | `/api/v1/teams` | Publish/update team assignments |
| `GET` | `/api/v1/teams/<yyyymmdd>` | Get teams from a date |
| `GET` | `/api/v1/players` | List registered players |

API write access will require an API key. Keys should be stored as hashes and shown only when first generated.

## Planned pages

| Route | Purpose |
| --- | --- |
| `/` | Public view of the current teams |
| `/login` | Sign in to an account |
| `/manage` | Administrator dashboard |
| `/manage/edit` | Edit, randomize, and publish teams |
| `/manage/api-key` | Manage API keys |
| `/manage/previous/<yyyymmdd>` | View a historical team snapshot |

Administrator pages will require authentication. Keeping a route unlinked from the homepage is not a substitute for access control.

## Tech stack

- **Backend:** Python, Flask
- **Database:** SQLite for local development; a production database such as MySQL for hosting
- **Frontend:** HTML, CSS, and JavaScript
- **API:** JSON over HTTP, versioned under `/api/v1/`

The exact structure and dependencies will be documented as implementation progresses.

## Development

The application is not yet implemented. Setup and run instructions will be added once the initial application structure is in place.

## Version roadmap

- [ ] Initial application and database structure
- [ ] Team viewing and administrator team editor
- [ ] Optional team randomizer and draft/publish workflow
- [ ] Individual view-only accounts for **1.0.0**
- [ ] Team history and REST API
- [ ] Player profile and availability features for **2.0.0**

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
