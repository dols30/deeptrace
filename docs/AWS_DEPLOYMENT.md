# AWS deployment: g5.xlarge with S3 and Bedrock

How to run DeepTrace on one AWS GPU instance. The same `docker-compose.yml` runs on the Mac. Production differs only in its env file, `.env.prod`, created from [`.env.prod.example`](../.env.prod.example).

```text
EC2 g5.xlarge (A10G 24 GB, 4 vCPU, 16 GiB)        same AWS account and region
┌───────────────────────────────────────────┐
│ frontend :3000 ─▶ backend :8080 ─▶ postgres │──▶ S3 bucket       recordings (record copy)
│                   └─ model workers (GPU)  │──▶ Bedrock          Nova Lite + Claude Haiku 4.5
└───────────────────────────────────────────┘
        ▲ ports bound to 127.0.0.1; reach them through SSH or SSM port forwarding
```

The workflow database stays in the Postgres container (Docker volume `deeptrace-pg`). Report media goes to S3; the container keeps a disposable cache. Credentials come from the instance role, and no AWS keys are stored on the host.

## 1. AWS account preparation (once)

1. **GPU quota.** In Service Quotas, set *Running On-Demand G and VT instances* to at least 4 vCPUs (8 to leave room to resize).
2. **Bedrock model access.** In the Bedrock console for the deployment region, enable **Amazon Nova Lite** and **Anthropic Claude Haiku 4.5**. Anthropic models require the one-time use-case form.
3. **S3 bucket.** Create it in the same region, with public access blocked, versioning, encryption and the lifecycle rule. Commands are in [S3_STORAGE.md](S3_STORAGE.md#create-the-bucket).
4. **Instance role** `deeptrace-ec2`, with this policy (replace the bucket name, and the region and account in the profile ARN). Add `AmazonSSMManagedInstanceCore` if you use SSM rather than SSH.

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "Media",
         "Effect": "Allow",
         "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:AbortMultipartUpload"],
         "Resource": "arn:aws:s3:::deeptrace-media-<team-suffix>/deeptrace/*"
       },
       {
         "Sid": "CaseAssistant",
         "Effect": "Allow",
         "Action": "bedrock:InvokeModel",
         "Resource": [
           "arn:aws:bedrock:us-east-1:<account-id>:inference-profile/us.amazon.nova-lite-v1:0",
           "arn:aws:bedrock:us-east-1:<account-id>:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
           "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
           "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0"
         ]
       }
     ]
   }
   ```

   The `us.` IDs are cross-region inference profiles, so Bedrock may serve a request from another US region. That is why the foundation-model ARNs use `*` for the region. The assistant calls `Converse`, which needs `bedrock:InvokeModel`. Bedrock reads videos over 20 MB by S3 reference with this same role.

## 2. Launch the instance

| Setting | Value |
| --- | --- |
| Type | `g5.xlarge` |
| AMI | AWS Deep Learning Base GPU AMI (Ubuntu 22.04 or 24.04): NVIDIA driver, Docker and the NVIDIA Container Toolkit preinstalled |
| Storage | 100 GB gp3 root volume (CUDA image, checkpoints, build cache) |
| IAM role | `deeptrace-ec2` |
| Security group | No inbound rules with SSM; otherwise SSH (22) from your IP only. Never open 3000/8000. |
| Metadata | IMDSv2 required, **hop limit 2** so containers can reach the instance role |

Set the hop limit on an existing instance with:

```bash
aws ec2 modify-instance-metadata-options --instance-id <id> --http-tokens required --http-put-response-hop-limit 2 --http-endpoint enabled
```

Check the GPU from the instance: `nvidia-smi` and `docker run --rm --gpus all ubuntu nvidia-smi`. Both should list the A10G.

## 3. Code and model assets

```bash
git clone --branch ec2 https://github.com/dols30/deeptrace.git deeptrace
cd deeptrace
```

`backend/models/` and `backend/vendor/` are not in Git. Copy them from the Mac (or the team's approved storage) before building, because the image bakes them in:

```bash
# from the Mac, in the repository root
rsync -avz --progress backend/models backend/vendor ubuntu@<host>:~/deeptrace/backend/
```

For the all-models profile, also run the asset check described in [ALL_MODELS_SETUP.md](ALL_MODELS_SETUP.md).

## 4. Configure `.env.prod`

```bash
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

Edit it: fresh passwords and JWT secret (`python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`), the bucket name and the region. What the file already sets:

- `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml`, which gives the backend the GPU
- `DEEPTRACE_TORCH_INDEX=cu126`, `DEEPTRACE_DEVICE=cuda`
- `DEEPTRACE_MODEL_WORKERS=true`, `DEEPTRACE_MAX_PARALLEL_RUNNERS=4`
- `DEEPTRACE_STORAGE_BACKEND=s3`, `DEEPTRACE_ASSISTANT_PROVIDER=bedrock`
- `DEEPTRACE_DEPLOYMENT_MODE=sandbox`, which refuses to start without auth, rejects auto-login and refuses Gemini

Do not add AWS keys or `AWS_BEARER_TOKEN_BEDROCK`, not even as empty values. Any of them overrides the instance role.

## 5. Build and run

Every compose command on the server takes `--env-file .env.prod`. A shell alias saves typing it:

```bash
alias dt='docker compose --env-file .env.prod'
dt up -d --build
dt ps                      # all three services healthy
```

## 6. Verify

```bash
dt exec backend python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
dt exec backend python -c "import boto3; print(boto3.client('sts').get_caller_identity()['Arn'])"   # ends in assumed-role/deeptrace-ec2/...
curl -fsS http://localhost:8000/health
```

Then, from your machine, open a tunnel and use the app at http://localhost:3000:

```bash
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 ubuntu@<host>
# or: aws ssm start-session --target <instance-id> --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'   (and again for 8000)
```

Upload a test file and check:

- `aws s3 ls s3://<bucket>/deeptrace/media/ --recursive` lists it.
- The case assistant answers with video observations, not only "from the case record".
- `dt logs backend` shows the `DEEPTRACE PROFILE` block. On the second upload, `model loading` should be near zero, and `nvidia-smi` lists one process per warm worker.

Before using GPU scores for review work, compare them against known CPU results, as described in [MODEL_ORCHESTRATION.md](MODEL_ORCHESTRATION.md#before-relying-on-gpu-scores). Thresholds were set on CPU runs.

## Operating it

| Task | Command |
| --- | --- |
| Deploy a new version | `git pull && dt up -d --build` |
| Logs | `dt logs -f backend` |
| Stop (keeps data) | `dt down`, then stop the instance to pay only for EBS |
| Back up the workflow DB | `dt exec -T postgres pg_dump -U deeptrace deeptrace \| gzip > deeptrace-$(date +%F).sql.gz` and copy it to S3 |
| Clear the media cache | Safe at any time; see [S3_STORAGE.md](S3_STORAGE.md#operations) |

`dt down -v` deletes the volumes, including the workflow database. Do not run it in production.

## Sizing and limits

- **Core profile on g5.xlarge:** three warm workers fit comfortably in 24 GB of VRAM and 16 GiB of RAM.
- **All-models profile:** up to seven workers plus TensorFlow (SOFTNet). That is tight in 16 GiB of RAM, so move to `g5.2xlarge` and set `DEEPTRACE_MODEL_PROFILE=all-models` in `.env.prod`.
- Not covered yet: a public HTTPS endpoint (ALB or CloudFront, which also needs `NEXT_PUBLIC_API_BASE_URL` and `DEEPTRACE_FRONTEND_ORIGINS` set to that origin), Cognito sign-in in Compose (it uses employee auth today), RDS instead of the Postgres container, and automated backups.
