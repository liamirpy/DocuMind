#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

cd "$ROOT_DIR"

DATA_DIR="$ROOT_DIR/data"







# ---------------------------------------------------
# Creating Data folder 
# ---------------------------------------------------


echo "Creating data folder..."

mkdir -p "$DATA_DIR"
echo "Data folder: $DATA_DIR"



# ---------------------------------------------------
# Define docker 
# ---------------------------------------------------



if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

echo "Validating Compose configuration..."

"${DOCKER[@]}" compose config --quiet





# ---------------------------------------------------
# Creating PostgreSQL file
# ---------------------------------------------------

echo "Creating PosgreSQL data directory"

mkdir -p "$DATA_DIR/postgreSQL"

echo "Data folder: $DATA_DIR/postgreSQL"

echo "Adding data diretory in PostgreSQL env file"

ENV_FILE="$ROOT_DIR/postgreSQL/.env"
touch "$ENV_FILE"

# Remove an existing DATA_DIR entry, then add the current value.
sed -i.bak '/^DATA_DIR=/d' "$ENV_FILE"
printf 'DATA_DIR=%s\n' "$DATA_DIR/postgreSQL" >> "$ENV_FILE"
rm -f "$ENV_FILE.bak"

echo "Saved DATA_DIR to $ENV_FILE for PostgreSQL"





# ---------------------------------------------------
# Creating users file 
# ---------------------------------------------------

echo "Creating user data (uploding) directory"

mkdir -p "$DATA_DIR/users"

echo "Data folder: $DATA_DIR/users"

echo "Adding data diretory in Node js env file"





# ---------------------------------------------------
# Build public Nginx
# ---------------------------------------------------

echo "Building Nginx..."

# "${DOCKER[@]}" compose build public-nginx

# "${DOCKER[@]}" compose up -d public-nginx



# ---------------------------------------------------
# Start PosgreSQL pgbouncer 
# ---------------------------------------------------



echo "Starting PostgreSQL/pgbouncer and public Nginx..."


# "${DOCKER[@]}" compose up -d \
#   postgres \
#   pgbouncer




# # ---------------------------------------------------
# # Start api and document worker 
# # ---------------------------------------------------

uid="$(id -u)"
gid="$(id -g)"

update_ids() {
  local env_file="$1"

  touch "$env_file"

  if grep -q '^HOST_UID=' "$env_file"; then
    sed -i "s/^HOST_UID=.*/HOST_UID=$uid/" "$env_file"
  else
    echo "HOST_UID=$uid" >> "$env_file"
  fi

  if grep -q '^HOST_GID=' "$env_file"; then
    sed -i "s/^HOST_GID=.*/HOST_GID=$gid/" "$env_file"
  else
    echo "HOST_GID=$gid" >> "$env_file"
  fi
}

update_ids "$ROOT_DIR/.env"
update_ids "$ROOT_DIR/paperMind/.env"





ENV_FILE="$ROOT_DIR/backend-api/.env"
touch "$ENV_FILE"

# Remove an existing DATA_DIR entry, then add the current value.
sed -i.bak '/^UPLOAD_DIR=/d' "$ENV_FILE"
printf 'UPLOAD_DIR=%s\n' "../data/users" >> "$ENV_FILE"
rm -f "$ENV_FILE.bak"

echo "Saved UPLOAD_DIR to $ENV_FILE for Node js"









# echo "%%%%%%%%%%%%%%%%%%%%%%%"


# "${DOCKER[@]}" compose up -d \
#   api \


# "${DOCKER[@]}" compose up -d \
#   document-worker \








# # ---------------------------------------------------
# # Start paperMind (agent and other services inside) , we only put the extractor-api behind nginx
# # ---------------------------------------------------


echo "Adding data diretory in paperMind env file"

ENV_FILE="$ROOT_DIR/paperMind/.env"
touch "$ENV_FILE"

# Remove an existing DATA_DIR entry, then add the current value.
sed -i.bak '/^HOST_ACCESS_ROOT=/d' "$ENV_FILE"
printf 'HOST_ACCESS_ROOT=%s\n' "$DATA_DIR" >> "$ENV_FILE"
rm -f "$ENV_FILE.bak"

echo "Saved HOST_ACCESS to $ENV_FILE for paperMind"



# ---------------------------------------------------
# Upload PostgreSQL schema 
# ---------------------------------------------------



##### for indexer define these too 

#######

# # Existing PDF-package outputs. This root is mounted read-only.
# DOCUMIND_INPUT_ROOT_HOST=/srv/DocuMind/data

# # The init service creates/fixes this writable output root automatically.
# DOCUMIND_OUTPUT_ROOT_HOST=/srv/DocuMind/data







"${DOCKER[@]}" compose up -d 





chmod +x "$ROOT_DIR/postgreSQL/apply_schema_nginx.sh"
bash "$ROOT_DIR/postgreSQL/apply_schema_nginx.sh"




# OPENSEARCH_USERNAME='admin' \
# OPENSEARCH_PASSWORD='Another_Strong_Password_2026!' \
# /srv/DocuMind/opensearch/setup.sh






# cd /srv/DocuMind

sudo docker compose exec -T opensearch \
  curl \
    --insecure \
    --user 'admin:DOCUMIND_opensearch_password_2026' \
    'https://127.0.0.1:9200/documind-chunks-v1/_count?pretty'






# # "${DOCKER[@]}" compose up -d \
# #   --build \
# #   --scale extractor-api=3 \
# #   grobid \
# #   extractor-api \
# #   extractor-load-balancer \
# #   ollama \
# #   ollama-model-init \
# #   agent-api




# # echo
# # echo "Container status:"

# # "${DOCKER[@]}" compose ps







# # ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# # ENV_FILE="$.env"

# # uid="$(id -u)"
# # gid="$(id -g)"

# # touch "$ENV_FILE"

# # if grep -q '^HOST_UID=' "$ENV_FILE"; then
# #   sed -i "s/^HOST_UID=.*/HOST_UID=$uid/" "$ENV_FILE"
# # else
# #   echo "HOST_UID=$uid" >> "$ENV_FILE"
# # fi

# # if grep -q '^HOST_GID=' "$ENV_FILE"; then
# #   sed -i "s/^HOST_GID=.*/HOST_GID=$gid/" "$ENV_FILE"
# # else
# #   echo "HOST_GID=$gid" >> "$ENV_FILE"
# # fi