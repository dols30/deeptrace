# S3 media storage

By default, uploaded recordings are kept on the API host's disk (`DEEPTRACE_REPORT_MEDIA_DIR`, `/data/report-media` in Docker). With `DEEPTRACE_STORAGE_BACKEND=s3`, the S3 bucket holds the record copy of each recording, and local disk only keeps a cache that can be deleted at any time.

Reports, findings and the workflow database are unchanged. They still live in SQLite/PostgreSQL. Only media files move.

## How it works

| Step | Local backend (default) | S3 backend |
| --- | --- | --- |
| Upload saved (`storage.persist_media`) | Copied to `<media dir>/<report_id>/<filename>`; that path is stored | Uploaded to `s3://<bucket>/<prefix>/media/<report_id>/<filename>`; that URI is stored; a copy goes to `<media dir>/s3-cache/` |
| Playback (`GET …/media`) | Served from disk | Served from the cache; downloaded from S3 first if missing |
| Case assistant | Reads the local file | Reads the cached file; Bedrock gets videos over 20 MB by S3 reference |
| Report deleted | File removed | Object deleted (a delete marker when versioning is on) and cache file removed |

Reads and deletes go by the stored value, not the current setting. Cases saved before switching to S3 keep their local paths and keep working; there is no automatic migration of existing files.

If the upload to S3 fails, the analysis still returns its report, marked `media_storage: unavailable`, exactly as a local disk failure does today. The investigator is told to download the report.

## Create the bucket

Use the same region as the API host and Bedrock. Bucket names are globally unique.

```bash
REGION=us-east-1
BUCKET=deeptrace-media-<team-suffix>

aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"   # outside us-east-1 add:
#   --create-bucket-configuration LocationConstraint=$REGION
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration '{"Rules":[{
  "ID":"expire-old-versions","Status":"Enabled","Filter":{},
  "NoncurrentVersionExpiration":{"NoncurrentDays":90},
  "AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}}]}'
```

- **Versioning** keeps a deleted or overwritten recording for 90 days, per the lifecycle rule. Change `NoncurrentDays` to your retention policy.
- **Encryption:** `AES256` (SSE-S3) is free. For an agency-managed key, use `aws:kms` with a KMS key ID; S3 Bucket Keys keep KMS request costs low.
- **Object Lock** (write-once retention) must be chosen when the bucket is created. Decide on it before creating a production bucket.

## Grant the API access

Attach to the EC2 instance role (or whatever identity runs the API):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
    "Resource": "arn:aws:s3:::deeptrace-media-<team-suffix>/deeptrace/*"
  }]
}
```

Bedrock reads videos over 20 MB by S3 reference using the same role, so `s3:GetObject` covers that too. Add `kms:Encrypt`, `kms:Decrypt` and `kms:GenerateDataKey` on the key if you use SSE-KMS.

In Docker on EC2, containers reach the instance role through the metadata service. Set the instance's IMDSv2 hop limit to 2:

```bash
aws ec2 modify-instance-metadata-options --instance-id <id> --http-put-response-hop-limit 2 --http-endpoint enabled
```

## Configure DeepTrace

In `.env.prod` on the server (already set in [`.env.prod.example`](../.env.prod.example)), or `.env` to try it from the Mac with AWS keys:

```bash
DEEPTRACE_STORAGE_BACKEND=s3
DEEPTRACE_S3_BUCKET=deeptrace-media-<team-suffix>
DEEPTRACE_S3_PREFIX=deeptrace
DEEPTRACE_AWS_REGION=us-east-1
```

Then `docker compose --env-file .env.prod up -d --build backend` (on the Mac, plain `docker compose up -d --build backend`). Startup fails if `DEEPTRACE_STORAGE_BACKEND=s3` is set without a bucket. Upload a test file and check that `aws s3 ls s3://$BUCKET/deeptrace/media/ --recursive` lists it.

## Operations

- **Cache:** `/data/report-media/s3-cache/` grows with every recording opened on this host. It is safe to delete at any time; files are downloaded again on the next read. There is no automatic eviction yet.
- **Cost:** roughly $0.023 per GB-month (S3 Standard, us-east-1), plus negligible request charges. Transfer between S3 and EC2/Bedrock in the same region is free.
- **Not yet covered:** moving existing local recordings into S3, presigned playback URLs (media is still served through the API), and cache eviction.
