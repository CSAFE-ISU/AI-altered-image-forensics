# CSAFE AI Altered Image Forensics

Flask app for tracking and analyzing AI-altered images. Python backend (`app.py`, `analysis.py`, `classifier.py`) with a vanilla JS/CSS frontend (`static/tracker.js`, `static/tracker.css`).

## Setup

```
pip3 install -r requirements.txt
```

## Running the app

```
PORT=5001 python3 app.py
```

Port 5000 is blocked by macOS AirPlay Receiver. Open http://localhost:5001 in a browser.

## Running tests

```
python3 -m pytest --cov=. --cov-report=term-missing --cov-fail-under=95
```

The project targets 95% test coverage. When adding new code, add tests to cover new branches and lines.

## Test conventions

- Tests live in `tests/`, organized by module: `test_analysis.py`, `test_helpers.py`, `test_routes_*.py`, etc.
- Use `conftest.py` fixtures (`app`, `client`, `tmp_base`, `sample_jpeg`, `sample_png`) rather than setting up your own filesystem or Flask app.
- Monkeypatch `flask_app._supabase` to `None` and redirect `BASE`, `DATA_FILE`, `IMAGE_ROOTS`, etc. to `tmp_path` so tests never touch the real filesystem or database.
- Do not use real Supabase credentials or real image files in tests.

## Code style

Run these before committing to keep code consistent:

```
black .
flake8 .
```

- Python: standard library imports first, then third-party, then local. No type annotations unless already present in the file.
- Add comments to all code except what is extremely obvious.
- Keep route handlers thin — business logic belongs in `analysis.py` or `classifier.py`, not `app.py`.
- Frontend is vanilla JS/CSS — no frameworks, no build step.

## Development workflow

For every change, follow these steps in order:

1. **Create a GitHub issue** if one doesn't already exist describing the work.
2. **Create a branch** named `<issue_num>-short-description` (e.g. `42-add-search-filter`) and branch off `main`.
3. **Make changes.**
4. **Run tests and coverage** — must pass with ≥95% coverage:
   ```
   python3 -m pytest --cov=. --cov-report=term-missing --cov-fail-under=95
   ```
5. **Update README** if the change affects setup, usage, or behaviour visible to users.
6. **Run linters:**
   ```
   black . && flake8 .
   ```
7. **Commit and push** the branch.
8. **Create a PR** referencing the issue (e.g. `Closes #42` in the PR body).
9. **Merge** the PR into `main`.

## Git conventions

- Commit messages use imperative mood, sentence case: `Add X`, `Fix Y`, `Update Z`.
- Reference GitHub issues when relevant: `Fix blank filename for existing records (issue #45)`.
- PR titles follow the same style as commit messages and stay under 70 characters.
