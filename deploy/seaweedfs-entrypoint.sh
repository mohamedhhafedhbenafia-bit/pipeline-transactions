#!/bin/sh
# Démarre SeaweedFS (master + volume + filer + passerelle S3) dans un seul conteneur,
# avec une identité S3 construite depuis S3_ACCESS_KEY / S3_SECRET_KEY.
set -eu

cat > /tmp/s3.json <<JSON
{
  "identities": [
    {
      "name": "pipeline",
      "credentials": [{"accessKey": "${S3_ACCESS_KEY}", "secretKey": "${S3_SECRET_KEY}"}],
      "actions": ["Admin", "Read", "Write", "List", "Tagging"]
    }
  ]
}
JSON

exec weed server \
  -dir=/data \
  -ip.bind=0.0.0.0 \
  -volume.max=0 \
  -master.volumeSizeLimitMB=64 \
  -s3 -s3.port=8333 -s3.config=/tmp/s3.json
