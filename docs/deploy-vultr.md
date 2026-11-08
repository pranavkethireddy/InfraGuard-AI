# Deploy InfraGuard on Vultr

One Vultr server runs everything behind one URL: Caddy serves the React app and forwards `/api` to the
FastAPI backend (including the live `/api/v1/ops/stream` events). The live fleet starts by itself on boot.
Any phone, iPad or laptop on any network opens `http://<server IP>`.

Incident explanations use **Vultr Serverless Inference** when `VULTR_INFERENCE_API_KEY` is set, then Gemini,
then the built-in fallback that needs no AI.

## 1. Account

1. Sign up at vultr.com and add credit (use the hackathon promo code if there is one).
2. **Serverless Inference:** in the console open *Serverless → Inference*, add a subscription, and copy its
   **inference API key**. This key is separate from the main Vultr account API key.

## 2. Server

1. *Deploy → Cloud Compute*: shared CPU, a region near the venue, **Ubuntu 24.04**, 2 vCPU / 4 GB RAM.
2. Add your SSH public key (`cat ~/.ssh/id_ed25519.pub`). Deploy, and note the server's IPv4 address.
3. Firewall: allow inbound TCP 22, 80 and 443.

## 3. Install and run

From the laptop:

```bash
ssh root@<IP> 'curl -fsSL https://get.docker.com | sh'
```

```bash
ssh root@<IP> 'git clone https://github.com/pranavkethireddy/InfraGuard-AI.git /opt/infraguard'
```

(For a private repository, run `gh auth login` on the server first, or copy the folder with `rsync`.)

Copy the secrets file (never commit it). It holds `GEMINI_API_KEY` and `VULTR_INFERENCE_API_KEY`:

```bash
scp backend/.env root@<IP>:/opt/infraguard/backend/.env
```

Start:

```bash
ssh root@<IP> 'cd /opt/infraguard && docker compose up -d --build'
```

Open `http://<IP>`. API docs: `http://<IP>/docs`.

## 4. Update after a merge

```bash
ssh root@<IP> 'cd /opt/infraguard && git pull && docker compose up -d --build'
```

## Optional: HTTPS with a domain

Point a domain's A record at the IP, then start with `SITE_ADDRESS=demo.example.com docker compose up -d`.
Caddy fetches the certificate itself.

## Settings used by the deploy

| Variable | Where | Meaning |
|---|---|---|
| `VULTR_INFERENCE_API_KEY` | backend/.env | Vultr Serverless Inference key; the agent tries it first |
| `VULTR_MODEL` | backend/.env | Model id; empty uses the first chat model the account offers |
| `GEMINI_API_KEY`, `GEMINI_API_KEY_2` | backend/.env | Backup AI provider |
| `LIVE_AUTOSTART` | docker-compose.yml | `true`: the live fleet loop starts when the server boots |
| `SITE_ADDRESS` | shell | `:80` (default, plain http on the IP) or a domain for HTTPS |

Run locally the same way: `docker compose up -d --build`, then open `http://localhost`.
