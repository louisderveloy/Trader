# A4 — Topologie Réseau Traefik

## Vue d'ensemble

Configuration réseau complète avec Traefik comme reverse proxy pour le développement local et la production.

---

## Architecture Globale

```
┌──────────────────────────────────────────────────────────────────┐
│                    Internet / Navigateur                         │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │    Traefik     │
              │ Reverse Proxy  │
              │  Port 80/443   │
              └────────┬───────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
  bot.localhost  api.localhost  grafana.localhost
         │             │             │
         ▼             ▼             ▼
   ┌─────────┐  ┌──────────┐  ┌──────────┐
   │Dashboard│  │   API    │  │ Grafana  │
   │ (Vue.js)│  │(FastAPI) │  │          │
   │Port 5173│  │Port 8000 │  │Port 3000 │
   └─────────┘  └────┬─────┘  └────┬─────┘
                     │             │
                     ▼             ▼
              ┌──────────────────────┐
              │   Redis (pub/sub)    │
              │      Port 6379       │
              └──────────────────────┘
                     ▲
                     │
                ┌────┴─────┐
                │   Bot    │
                │ (Python) │
                └────┬─────┘
                     │
                     ▼
              ┌──────────────────────┐
              │   PostgreSQL +       │
              │   TimescaleDB        │
              │      Port 5432       │
              └──────────────────────┘
```

---

## Environnement Local (dev)

### Sous-domaines

| Service | Domaine | Port interne | Port externe |
|---------|---------|--------------|--------------|
| Dashboard | `bot.localhost` | 5173 | 443 (HTTPS) |
| API | `api.localhost` | 8000 | 443 (HTTPS) |
| Grafana | `grafana.localhost` | 3000 | 443 (HTTPS) |
| Traefik Dashboard | `localhost` | 8080 | 8080 (HTTP) |

### Configuration Traefik (dev)

```yaml
# docker-compose.yml
traefik:
  command:
    - "--api.insecure=true"
    - "--providers.docker=true"
    - "--providers.docker.exposedbydefault=false"
    - "--entrypoints.web.address=:80"
    - "--entrypoints.websecure.address=:443"
    - "--entrypoints.websecure.http.tls=true"
  ports:
    - "80:80"
    - "443:443"
    - "8080:8080"
```

### HTTPS Local (mkcert)

Pour le développement local, utiliser `mkcert` pour générer des certificats auto-signés :

```bash
# Installer mkcert
# Windows (avec chocolatey)
choco install mkcert

# Linux/Mac
brew install mkcert

# Installer le CA local
mkcert -install

# Générer les certificats pour les domaines locaux
mkcert bot.localhost api.localhost grafana.localhost localhost 127.0.0.1 ::1

# Les certificats sont générés dans le répertoire courant
# Copier dans traefik/certs/
mkdir -p traefik/certs
mv *.pem traefik/certs/
```

Puis configurer Traefik pour utiliser ces certificats (voir configuration avancée ci-dessous).

---

## Environnement Production (VPS)

### Sous-domaines

Remplacer `yourdomain.com` par votre domaine réel.

| Service | Domaine | Port interne | Port externe |
|---------|---------|--------------|--------------|
| Dashboard | `bot.yourdomain.com` | 5173 | 443 (HTTPS) |
| API | `api.yourdomain.com` | 8000 | 443 (HTTPS) |
| Grafana | `grafana.yourdomain.com` | 3000 | 443 (HTTPS) |

### Configuration Traefik (prod)

```yaml
# docker-compose.prod.yml
traefik:
  command:
    - "--api.dashboard=false"  # Désactiver le dashboard en prod
    - "--providers.docker=true"
    - "--providers.docker.exposedbydefault=false"
    - "--entrypoints.web.address=:80"
    - "--entrypoints.websecure.address=:443"
    # Let's Encrypt configuration
    - "--certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL}"
    - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
    # Redirect HTTP to HTTPS
    - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
    - "--entrypoints.web.http.redirections.entrypoint.scheme=https"
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
    - traefik_certs:/letsencrypt
```

### Labels Docker pour chaque service

```yaml
# Exemple pour le dashboard
dashboard:
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.dashboard.rule=Host(`bot.yourdomain.com`)"
    - "traefik.http.routers.dashboard.entrypoints=websecure"
    - "traefik.http.routers.dashboard.tls=true"
    - "traefik.http.routers.dashboard.tls.certresolver=letsencrypt"
    - "traefik.http.services.dashboard.loadbalancer.server.port=5173"
```

---

## Réseau Docker

### Configuration réseau

```yaml
networks:
  trader-network:
    driver: bridge
```

### Communication inter-services

Les services communiquent entre eux via le réseau `trader-network` en utilisant le nom du service comme hostname :

- Bot → API : Non (le bot publie sur Redis uniquement)
- Bot → Redis : `redis://redis:6379/0`
- Bot → PostgreSQL : `postgresql://postgres:5432/trader_bot`
- API → Redis : `redis://redis:6379/0`
- API → PostgreSQL : `postgresql://postgres:5432/trader_bot`
- Dashboard → API : `https://api.localhost` (ou `https://api.yourdomain.com` en prod)
- Grafana → PostgreSQL : `postgres:5432`

---

## Configuration DNS (Production)

Configurer les enregistrements DNS suivants pour votre domaine :

```
Type    Name        Value              TTL
A       @           <VPS_IP>           3600
A       bot         <VPS_IP>           3600
A       api         <VPS_IP>           3600
A       grafana     <VPS_IP>           3600
```

Ou utiliser un wildcard :

```
Type    Name        Value              TTL
A       @           <VPS_IP>           3600
A       *           <VPS_IP>           3600
```

---

## Sécurité

### Firewall VPS

Ouvrir uniquement les ports nécessaires :

```bash
# UFW (Ubuntu/Debian)
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP (redirect vers HTTPS)
ufw allow 443/tcp  # HTTPS
ufw enable
```

### HTTPS Only

En production, tout le trafic HTTP doit être redirigé vers HTTPS automatiquement (voir configuration Traefik prod ci-dessus).

### Rate Limiting (optionnel)

Ajouter du rate limiting sur Traefik pour protéger l'API :

```yaml
# labels API
- "traefik.http.middlewares.api-ratelimit.ratelimit.average=100"
- "traefik.http.middlewares.api-ratelimit.ratelimit.burst=50"
- "traefik.http.routers.api.middlewares=api-ratelimit"
```

---

## Troubleshooting

### Vérifier les routes Traefik

Accéder au dashboard Traefik (dev uniquement) : `http://localhost:8080`

### Tester la résolution DNS locale

```bash
# Windows
nslookup bot.localhost
nslookup api.localhost
nslookup grafana.localhost

# Linux/Mac
dig bot.localhost
dig api.localhost
dig grafana.localhost
```

### Logs Traefik

```bash
docker logs trader-traefik
```

### Tester les certificats HTTPS

```bash
# Dev (auto-signés)
curl -k https://bot.localhost

# Prod (Let's Encrypt)
curl https://bot.yourdomain.com
openssl s_client -connect bot.yourdomain.com:443 -servername bot.yourdomain.com
```

---

## Annexes

### Configuration avancée Traefik pour mkcert (dev)

Si vous souhaitez utiliser les certificats mkcert en développement :

```yaml
# traefik/traefik.yml
providers:
  file:
    filename: /etc/traefik/dynamic.yml

# traefik/dynamic.yml
tls:
  certificates:
    - certFile: /certs/bot.localhost+6.pem
      keyFile: /certs/bot.localhost+6-key.pem
```

Puis monter les certificats dans le container Traefik :

```yaml
traefik:
  volumes:
    - ./traefik/traefik.yml:/etc/traefik/traefik.yml
    - ./traefik/dynamic.yml:/etc/traefik/dynamic.yml
    - ./traefik/certs:/certs:ro
```
