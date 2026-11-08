# Backend Documentation Index

This page replaces an obsolete implementation guide for the former Firestore
backend. The current service uses FastAPI and PostgreSQL; route definitions and
the security contracts below are maintained with the code.

## Sources of Truth

- [Backend setup, routes and response envelope](../README.md)
- [Bot conversation profile](BOT_CONVERSATION_PROFILE.md)

## Runtime Boundaries

- FastAPI routes are registered from `backend/main.py` and `backend/routes/`.
- PostgreSQL access is implemented through SQLAlchemy models and services.
- Administrator requests use JWT authentication; bot routes use the bot key.
- Interactive API documentation is available only when both
  `ENVIRONMENT=development` and `API_DOCS_ENABLED=true` are configured.
- JSON responses use the shared envelope. Error responses contain `data: null`
  and registered machine-readable message codes.

Do not use archived issue lists, Firestore examples, or old endpoint
descriptions as API contracts. The checked-in OpenAPI schemas and the README
are the current documentation inputs; changes to either must be reviewed with
the route implementation and its tests.
