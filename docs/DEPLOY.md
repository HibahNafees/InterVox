# Deploying AI Mock Interviewer

Everything here is free: Oracle Cloud Always Free (API + MySQL), DuckDNS (a
hostname for HTTPS), Vercel Hobby (the React app). The only paid service stays
the Fire API, capped at $1/month by the app.

```
browser ──https──> Vercel (React)          ──https──> intervox.duckdns.org
                                                       Caddy (TLS) ─> gunicorn/Flask ─> MySQL
                                                       (Oracle VM, docker compose)
```

## 1. Accounts (one time)

1. **Oracle Cloud Free Tier** — sign up at cloud.oracle.com. The card is only an
   identity check; Always Free resources aren't charged. Right after signing up,
   create a **budget alert at $1** (Billing → Budgets) so any accidental paid
   resource emails you.
2. **DuckDNS** — sign in at duckdns.org, the subdomain is `intervox`
   (intervox.duckdns.org); keep the token page open.
3. **Vercel** — sign up with GitHub at vercel.com (Hobby plan).

## 2. The Oracle VM

1. Compute → Instances → Create: image **Ubuntu 24.04**, shape **VM.Standard.A1.Flex**
   (Ampere, Always Free) with **2 OCPU / 12 GB**. Add your SSH public key.
2. Networking → the instance's subnet → Security List → add ingress rules for
   TCP **80** and **443** from `0.0.0.0/0`.
3. Oracle's Ubuntu images also block ports in iptables. On the VM:
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```
4. In DuckDNS, set your subdomain's IP to the VM's **public IP**.
5. Install Docker and get the code:
   ```bash
   sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
   sudo usermod -aG docker $USER && newgrp docker
   git clone https://github.com/HibahNafees/InterVox.git && cd InterVox
   cp deploy/env.example .env && chmod 600 .env
   nano .env      # fill every value; generate secrets with the command in the file
   ```
   `API_DOMAIN` is your DuckDNS name. Paste the Fire key into `FIRE_API_KEY`
   here only — never into git or the frontend. Leave `CORS_ORIGINS` as a
   placeholder until step 3 gives you the Vercel URL.
6. Start it:
   ```bash
   docker compose up -d --build
   docker compose ps                 # db healthy, api healthy, caddy and purge up
   curl https://$API_DOMAIN/api/health
   ```
   The API refuses to start with weak secrets, SQLite, a localhost CORS origin
   or a missing Fire key (`docker compose logs api` says which).

## 2b. Alternative: the devbox (current host)

Oracle refused the sign-up, so the API runs on the devbox, where nginx and
certbot already own ports 80/443. Point the DuckDNS name at the devbox's
public IP, then run the same stack with Caddy off:

```bash
sudo git clone https://github.com/HibahNafees/InterVox.git /srv/intervox
sudo chown -R $USER: /srv/intervox && cd /srv/intervox
cp deploy/env.example .env && chmod 600 .env      # fill it as in step 2.5
docker compose -f docker-compose.yml -f deploy/compose.devbox.yml up -d --build
sudo cp deploy/nginx-intervox.conf /etc/nginx/sites-available/intervox
sudo ln -s /etc/nginx/sites-available/intervox /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d intervox.duckdns.org
curl https://intervox.duckdns.org/api/health
```

The production database is its own MySQL container, separate from the dev
database. Updates: `git pull` then the same `docker compose ... up -d --build`.
If Oracle ever works out, move with a backup (section 4) and the same `.env`.

## 3. The frontend on Vercel

1. Vercel → Add New → Project → import the GitHub repo.
2. **Root Directory: `frontend`** (framework Vite is detected; `vercel.json`
   handles page routes and security headers).
3. Environment variable: `VITE_API_URL` = `https://intervox.duckdns.org`
   (no trailing slash, no `/api`).
4. Deploy, then copy the production URL (e.g. `https://ai-mock-interviewer.vercel.app`).
5. Back on the VM, set `CORS_ORIGINS` to that URL in `.env` and run
   `docker compose up -d` to apply it.
6. Open the Vercel URL, sign up, and run a short interview. Microphone access
   needs HTTPS, which both Vercel and Caddy provide.

## 4. Running it

- **Admin page:** put your email in `ADMIN_EMAILS`; `/admin` shows daily usage,
  Fire spend and budget left. New sessions pause automatically at $1/month.
- **Update:** `git pull && docker compose up -d --build` (migrations run on start).
- **Logs:** `docker compose logs -f api`.
- **Backups** (daily at 03:00, keeps 14): `crontab -e` and add
  `0 3 * * * $HOME/InterVox/deploy/backup.sh` (on the devbox, `/srv/intervox/deploy/backup.sh`). Restore with
  `gunzip -c ~/backups/db-DATE.sql.gz | docker compose exec -T db sh -c 'mysql -u mock -p"$MYSQL_PASSWORD" mock_interviewer'`.
- **Expired documents** are deleted daily by the `purge` service.
- **Sales demo** (T-166): `docker compose exec -T api flask demo-reset` deletes and
  re-seeds the fictional "Northstar Career Partners" org (no Fire calls). Run it
  nightly from root's crontab so dates, streaks and the demo's edits stay fresh:
  `30 4 * * * cd /srv/intervox && docker compose -f docker-compose.yml -f deploy/compose.devbox.yml exec -T api flask demo-reset >> /var/log/intervox-demo.log 2>&1`.
  `ORG_FEATURE` (`off` / `admin_only` / `on`, default `admin_only`) decides who
  can see organizations; demo accounts open only from `/admin` (View as).
- **Before each deploy:** `cd frontend && npm audit` (should report 0).

## 5. Local check of the stack

The same compose file runs on any machine with Docker. For a plain-HTTP test,
use a separate env file with `API_DOMAIN=:80`, `HTTP_PORT=8088` and
`ENV_FILE=<that file>`, then
`docker compose -p mitest --env-file <that file> up -d --build` and
`curl http://127.0.0.1:8088/api/health`. Point `FIRE_BASE_URL` at a dead
address (e.g. `http://127.0.0.1:9`) so a smoke test can't spend.
