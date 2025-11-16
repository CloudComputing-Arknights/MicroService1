# User & Address Microservice (FastAPI + Cloud SQL)

This repository provides the atomic User/Address microservice for a Neighborhood Exchange project for COMS4153.
It exposes a standalone API responsible solely for user profiles, address records, and authentication, and is designed to be consumed by higher-level composite services.

The microservice follows a clean API-first approach using FastAPI, Pydantic v2 models, JWT-based authentication, and a MySQL Cloud SQL backend deployed on Cloud Run.

## Key Features

### 1. Users

- Create, read, update, delete (CRUD)
- Public / Private / Admin views
- Password hashing & secure storage
- JWT-based authentication & role management
- Pagination, filtering, and query caching
- HAL-style _links in responses

### 2. Addresses

- Atomic CRUD for address records
- Filtering & pagination
- Response caching with ETag-based validation
- Clean separation from User model (no foreign keys in atomic MS)

### 3. Authentication

- OAuth2 Password Grant via /auth/token
- Access tokens with expiry, role, and subject fields
- Secure password hashing via bcrypt_sha256

### 4. Caching

- Uses cachetools.TTLCache:
- Object cache for User/Address by ID
- List cache for filtered queries
- Automatic invalidation on update/delete

### 5. Database Integration

- Async MySQL via aiomysql + SQLAlchemy
- Cloud SQL connection through Unix domain socket
- Environment-based configuration

## Local Development

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Set environment variables

```powershell
DB_PASS=your-db-password
INSTANCE_CONNECTION_NAME=project:region:instance
DB_NAME=users_db
DB_USER=users_svc
JWT_SECRET=your-local-secret
```

### 3. Run locally
   
```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Visit API docs

```powershell
http://localhost:8000/docs
```

## Deployment (Cloud Run)
This service is designed specifically for Cloud Run.
```
gcloud builds submit --tag gcr.io/<PROJECT_ID>/user-address-ms
gcloud run deploy user-address-ms \
  --image gcr.io/<PROJECT_ID>/user-address-ms \
  --platform managed \
  --region <REGION> \
  --add-cloudsql-instances $INSTANCE_CONNECTION_NAME \
  --set-env-vars INSTANCE_CONNECTION_NAME=$INSTANCE_CONNECTION_NAME \
  --set-secrets DB_PASS=db-pass:latest \
  --set-env-vars JWT_SECRET="(your secret or Secret Manager)"
```

## API overview

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/auth/token` | Obtain access token |
| GET    | `/auth/me` | Retrieve current user |
| GET    | `/admin/users` | Admin-only listing |

### Users

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/users` | Create user |
| GET    | `/users?filters...` | List users (paginated + filtered) |
| GET    | `/users/{id}` | Read full user |
| GET    | `/users/{id}/public` | Public view |
| GET    | `/users/{id}/private` | Owner/Admin view |
| GET    | `/admin/users/{id}` | Admin view |
| PUT    | `/users/{id}` | Update |
| DELETE | `/users/{id}` | Delete |

### Addresses

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/addresses` | Create address |
| GET    | `/addresses?filters...` | List addresses |
| GET    | `/addresses/{id}` | Retrieve address |
| PUT    | `/addresses/{id}` | Update |
| DELETE | `/addresses/{id}` | Delete |

## Testing

Use the built-in OpenAPI UI:
```powershell
/docs
```

Or test via cURL:
```powershell
curl -X POST http://localhost:8000/auth/token \
  -d "username=alice&password=Str0ngP@ss!"
```

## Authentication Model
JWT payload:
```powershell
{
  "sub": "USER_ID",
  "username": "alice",
  "role": "user",
  "exp": "timestamp"
}
```
Roles:
*   `user`
*   `admin`
## Design Notes
### Atomic service principles implemented
- No cross-service joins
- No user↔address relational coupling
- All relations handled by composite layer
- Pure CRUD with stable, predictable contracts

### Why no `user_id` in Address?
Because higher-level composite microservices (e.g., Trade or Exchange services) build their own cross-entity relations.
This keeps atomic microservices clean, isolated, and scalable.

## Requirements

See `requirements.txt`. Typical dependencies include `fastapi`, `uvicorn`, and `pydantic`.


