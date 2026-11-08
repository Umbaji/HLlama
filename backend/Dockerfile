FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY . .

EXPOSE 8000

# The documentary base is ingested by the application itself when it starts,
# in the background: the passages of the documents live in the database, and
# nothing else puts them there. A failure of the ingestion does not stop the
# app - an outage is worse than an empty base - but it is reported, and the
# deployment fails on it.
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
