# Basketball Teams

A web application for organizing players into basketball teams, publishing daily assignments, and viewing previous team arrangements.

Built with **Python and Flask**. This project is currently in early development.

## Planned features

### Team management
- View the currently published teams on a public homepage.
- Manually assign players to teams and move players between teams.
- Optionally generate teams by shuffling all registered players, regardless of their current assignments.
- Reroll randomized teams before publishing.
- Adjust randomized assignments manually.
- Keep edits as a draft until an administrator publishes them.

### Accounts

**Version 1.0.0 — View-only accounts**
- Each friend has an individual account.
- Friends can sign in, view current teams and past team history, and change their own password.
- Friend accounts cannot edit team assignments or player details.
- Administrators can create, disable, and reset accounts.

**Version 2.0.0 — Interactive profiles**
- Friends will be able to manage their own player profile.
- Planned profile options include display-name and availability management.

### Team history
- Save a snapshot whenever an administrator publishes a team arrangement.
- Browse previously published arrangements.
- Keep published snapshots immutable.
- Restoring an older arrangement will create a new publication rather than overwrite history.

### REST API

A versioned REST API will let authorized API-key holders read and update the same team data used by the website.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/teams` | Get the current teams |
| `PUT` | `/api/v1/teams` | Update the current team assignments |
| `GET` | `/api/v1/teams/<yyyymmdd>` | Get teams from a particular date |
| `GET` | `/api/v1/players` | List registered players |

API write access will require an API key. Keys will be stored securely as hashes and shown only when first generated.

## Planned pages

| Route | Purpose |
| --- | --- |
| `/` | Public view of the current teams |
| `/login` | Sign in to an account |
| `/logout` | Sign out |
| `/account` | View account details and change password |
| `/manage` | Administrator dashboard |
| `/manage/edit` | Edit, randomize, and publish teams |
| `/manage/api-key` | Manage API keys |
| `/manage/previous/<yyyymmdd>` | View a historical team snapshot |

Administrator routes will require authentication and authorization. Hiding a route or leaving it out of the homepage navigation is not a security measure.

## Technology

- **Backend:** Python and Flask
- **Database:** SQLite for local development; a production database such as MySQL may be used for hosting
- **Frontend:** HTML, CSS, and JavaScript
- **API:** JSON over HTTP, versioned under `/api/v1/`

The final dependencies and project structure will be documented as implementation progresses.

## Development status

The application has not been implemented yet. Installation and run instructions will be added once the initial application structure is ready.

## Roadmap

- [ ] Define the initial application structure and database schema
- [ ] Build the public team-viewing page
- [ ] Build the administrator dashboard and team editor
- [ ] Add random team generation and draft/publish workflow
- [ ] Add team history
- [ ] Add the REST API and API-key management
- [ ] Add individual view-only accounts for version **1.0.0**
- [ ] Add interactive player profiles for version **2.0.0**

## License

No license has been selected yet. Until a license is added, the project remains under the default copyright terms.
