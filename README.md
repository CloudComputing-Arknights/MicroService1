# Sprint1_MicroService1

Lightweight FastAPI microservice providing simple User and Address models and endpoints. This repository is a demo project used for Cloud Computing exercises (Sprint 1).

## What this project contains

- `main.py` - FastAPI application and HTTP endpoints (health, users, addresses).
- `models/` - Pydantic v2 models for `User`, `Address`, and `Health` responses.
- `requirements.txt` - Python dependencies required to run the app.



## Quickstart (run locally)

1. Create and activate a Python virtual environment (recommended).

PowerShell example:

```powershell
python -m venv .venv;
. .\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Start the app with Uvicorn:

```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

4. Open the interactive OpenAPI docs in your browser:

    http://127.0.0.1:8000/docs



## API overview

Main endpoints (status codes shown are typical):

- `GET /` — Root message (200)
- `GET /health` — Health check (200). Optional query param `echo`.
- `GET /health/{path_echo}` — Health check with path echo (200).

Address endpoints (NOT fully implemented in the starter code):

- `POST /addresses` — Create an address (201)
- `GET /addresses` — List addresses (200)
- `GET /addresses/{address_id}` — Get a single address (200)
- `PUT /addresses/{address_id}` — Update an address (200)
- `DELETE /addresses/{address_id}` — Delete an address (204)

User endpoints (NOT fully implemented in the starter code):

- `POST /users` — Create user (201)
- `GET /users` — List users (200)
- `GET /users/{user_id}` — Get a user (200)
- `PUT /users/{user_id}` — Update user (200)
- `DELETE /users/{user_id}` — Delete user (204)

Note: Many endpoint handlers currently raise `HTTPException(status_code=501, detail="NOT IMPLEMENTED")` as placeholders.

## Models

Key Pydantic models are in the `models/` package:

- `models.user` — `UserCreate`, `UserRead`, `UserUpdate`, and base user schemas. Users embed addresses.
- `models.address` — `AddressCreate`, `AddressRead`, `AddressUpdate`, and base address schemas.
- `models.health` — `Health` model returned by health endpoints.

Open the Python files under `models/` to see full field definitions and example JSON in the Pydantic `model_config`.

## Development notes

- The application uses in-memory dictionaries (`users`, `addresses` in `main.py`) as a temporary datastore. Persistence is intentionally out of scope for this sprint.
- To implement full functionality, replace the in-memory stores with a real database or persistent layer.


## Requirements

See `requirements.txt`. Typical dependencies include `fastapi`, `uvicorn`, and `pydantic`.


