#!/bin/bash
# Runs once, when the `db` volume is first created: a separate database + user for Keycloak.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    CREATE USER keycloak WITH PASSWORD '${KC_DB_PASSWORD}';
    CREATE DATABASE keycloak OWNER keycloak;
SQL
