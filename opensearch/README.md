curl \
  "http://localhost:9200/documind-chunks-v1/_mapping?pretty"









  curl \
  --request DELETE \
  "http://localhost:9200/documind-chunks-v1/_doc/chunk-001?pretty"






  curl \
  --request DELETE \
  "http://localhost:9200/documind-chunks-v1?pretty"




  sudo docker compose down

sudo mkdir -p /srv/documind_database/opensearch

sudo chown -R 1000:1000 /srv/documind_database/opensearch

sudo chmod -R 750 /srv/documind_database/opensearch

sudo docker compose up -d
