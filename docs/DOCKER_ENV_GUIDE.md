# Guide Docker : Dev vs Prod & Gestion des .env

## Comment Docker Choisit entre Dev et Prod

### Principe Fondamental

Docker **ne choisit pas automatiquement** entre dev et prod. C'est **vous** qui choisissez en spécifiant quel fichier docker-compose utiliser :

```bash
# Mode développement (par défaut)
docker-compose up -d
# équivaut à:
docker-compose -f docker-compose.yml up -d

# Mode production
docker-compose -f docker-compose.prod.yml up -d
```

### Fichiers docker-compose

| Fichier | Usage | Volumes | Hot Reload |
|---------|-------|---------|------------|
| `docker-compose.yml` | **Développement** | Bind mounts vers `./volumes/` | ✅ Oui |
| `docker-compose.prod.yml` | **Production** | Docker named volumes | ❌ Non |

---

## Gestion des Variables d'Environnement (.env)

### Un Seul Fichier .env

**Docker Compose lit toujours le fichier `.env` à la racine du projet**, peu importe le fichier docker-compose utilisé.

```
/Trader
├── .env                    ← Docker lit TOUJOURS ce fichier
├── docker-compose.yml      ← Dev
├── docker-compose.prod.yml ← Prod
```

### Comment Différencier Dev et Prod ?

#### Option 1 : Variable ENVIRONMENT dans .env (Recommandé)

```bash
# .env
ENVIRONMENT=dev  # ou 'prod'
```

Les services peuvent lire cette variable :

```yaml
# docker-compose.yml
bot:
  environment:
    ENVIRONMENT: ${ENVIRONMENT:-dev}
```

#### Option 2 : Fichiers .env Séparés (Avancé)

Si vous voulez des `.env` différents pour dev et prod :

```bash
# Créer .env.dev et .env.prod
cp .env.example .env.dev
cp .env.example .env.prod

# Modifier chaque fichier avec ses paramètres

# Utiliser avec --env-file
docker-compose --env-file .env.dev up -d
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

**⚠️ Attention :** Cette approche est plus complexe. Pour 99% des cas, utilisez Option 1.

---

## Différences Dev vs Prod

### docker-compose.yml (Dev)

```yaml
volumes:
  # Bind mount → données dans ./volumes/postgres/
  - ./volumes/postgres:/var/lib/postgresql/data

  # Code monté pour hot reload
  - ./bot:/app

environment:
  ENVIRONMENT: ${ENVIRONMENT:-dev}
  API_RELOAD: true  # Auto-reload sur changement de code
  DEBUG: true
```

**Avantages Dev:**
- ✅ Données visibles dans le projet (`./volumes/`)
- ✅ Hot reload automatique
- ✅ Facile de nettoyer (supprimer `./volumes/`)
- ✅ Peut éditer le code et voir les changements immédiatement

### docker-compose.prod.yml (Prod)

```yaml
volumes:
  # Named volume → géré par Docker, isolé
  postgres_data:

  # Pas de bind mount du code
  # (le code est copié dans l'image au build)

environment:
  ENVIRONMENT: prod
  API_RELOAD: false  # Pas de reload
  API_WORKERS: 4     # Multiple workers
  DEBUG: false
```

**Avantages Prod:**
- ✅ Volumes gérés par Docker (performances, backups)
- ✅ Code immutable (pas de modifications accidentelles)
- ✅ Multiple workers pour API
- ✅ Pas de debug overhead

---

## Workflow Typique

### Développement Local

```bash
# 1. Créer .env depuis .env.example
cp .env.example .env

# 2. Éditer .env
nano .env
# Mettre ENVIRONMENT=dev
# Configurer BINANCE_TESTNET=true

# 3. Démarrer les services
docker-compose up -d

# 4. Voir les logs
docker-compose logs -f bot

# 5. Arrêter les services
docker-compose down

# 6. Nettoyer les volumes (ATTENTION: perte de données)
rm -rf volumes/postgres volumes/redis volumes/grafana
```

### Déploiement Production

```bash
# 1. Sur le serveur VPS, créer .env
nano .env
# Mettre ENVIRONMENT=prod
# BINANCE_TESTNET=false (pour le mainnet)
# Changer tous les mots de passe par défaut !

# 2. Démarrer avec le fichier prod
docker-compose -f docker-compose.prod.yml up -d

# 3. Vérifier les logs
docker-compose -f docker-compose.prod.yml logs -f

# 4. Arrêter (sans supprimer les volumes)
docker-compose -f docker-compose.prod.yml down

# 5. Backup des volumes (IMPORTANT)
docker run --rm -v trader_postgres_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz -C /data .
```

---

## Variables d'Environnement Importantes

### Toujours dans .env

```bash
# Exchange
BINANCE_TESTNET=true  # false en prod
BINANCE_TESTNET_API_KEY=...
BINANCE_MAINNET_API_KEY=...  # Seulement en prod

# Database
POSTGRES_PASSWORD=dev_password  # CHANGER EN PROD !
JWT_SECRET_KEY=...  # CHANGER EN PROD !

# Notifications
DISCORD_WEBHOOK_URL=...
```

### Définies dans docker-compose

```yaml
# Ces variables sont définies dans docker-compose.yml ou docker-compose.prod.yml
ENVIRONMENT: ${ENVIRONMENT:-dev}
DATABASE_URL: postgresql+asyncpg://...
REDIS_URL: redis://redis:6379/0
```

---

## Volumes : Bind Mounts vs Named Volumes

### Bind Mounts (Dev)

```yaml
volumes:
  - ./volumes/postgres:/var/lib/postgresql/data
```

**Caractéristiques:**
- Données stockées dans `G:\dev\Trader\volumes\postgres\`
- Visible dans l'explorateur de fichiers
- Facile à backup (copier le dossier)
- Peut avoir des problèmes de permissions (Windows/Linux)

### Named Volumes (Prod)

```yaml
volumes:
  postgres_data:  # Défini en haut du fichier

services:
  postgres:
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

**Caractéristiques:**
- Données stockées par Docker (Linux: `/var/lib/docker/volumes/`)
- Pas visible directement dans l'explorateur
- Géré par Docker (performances optimisées)
- Backup via commandes Docker

**Lister les volumes:**
```bash
docker volume ls

# Inspecter un volume
docker volume inspect trader_postgres_data
```

---

## FAQ

### Q: Puis-je avoir .env.dev et .env.prod en même temps ?

Oui, mais ce n'est pas recommandé pour débuter. Utilisez plutôt :

```bash
# .env (pour dev)
ENVIRONMENT=dev
BINANCE_TESTNET=true

# Sur le serveur prod, éditez .env directement
ENVIRONMENT=prod
BINANCE_TESTNET=false
```

### Q: Comment passer de dev à prod ?

```bash
# 1. Arrêter dev
docker-compose down

# 2. Modifier .env
nano .env
# Changer ENVIRONMENT=dev → ENVIRONMENT=prod
# Changer BINANCE_TESTNET=true → false
# Changer tous les mots de passe !

# 3. Démarrer prod
docker-compose -f docker-compose.prod.yml up -d
```

### Q: Mes données sont où en dev ?

Dans `./volumes/` à la racine du projet :

```
volumes/
├── postgres/  ← Base de données PostgreSQL
├── redis/     ← Données Redis
├── grafana/   ← Configuration Grafana
├── traefik/   ← Certificats HTTPS
└── bot_logs/  ← Logs du bot
```

Ces dossiers sont ignorés par git (dans `.gitignore`).

### Q: Comment nettoyer les volumes en dev ?

```bash
# Arrêter les services
docker-compose down

# Supprimer les volumes
rm -rf volumes/postgres volumes/redis volumes/grafana volumes/traefik volumes/bot_logs

# Ou tout supprimer
rm -rf volumes/*

# Recréer les dossiers
mkdir -p volumes/postgres volumes/redis volumes/grafana volumes/traefik volumes/bot_logs

# Redémarrer
docker-compose up -d
```

### Q: Comment nettoyer les volumes en prod ?

**⚠️ ATTENTION: Perte de données !**

```bash
# Lister les volumes
docker volume ls

# Supprimer un volume spécifique
docker volume rm trader_postgres_data

# Ou tout supprimer (après docker-compose down)
docker-compose -f docker-compose.prod.yml down -v
```

### Q: Docker lit quel .env exactement ?

Docker Compose lit **toujours** `.env` à la racine du projet, sauf si vous spécifiez `--env-file` :

```bash
# Lit .env
docker-compose up -d

# Lit .env.custom
docker-compose --env-file .env.custom up -d
```

---

## Résumé

| Question | Réponse |
|----------|---------|
| **Comment Docker choisit dev/prod ?** | Vous choisissez avec `-f docker-compose.prod.yml` |
| **Quel .env est utilisé ?** | Toujours `.env` (sauf `--env-file`) |
| **Où sont les données en dev ?** | `./volumes/` dans le projet |
| **Où sont les données en prod ?** | Volumes Docker (gérés par Docker) |
| **Comment différencier dev/prod ?** | Variable `ENVIRONMENT` dans `.env` |
| **Hot reload en prod ?** | Non, désactivé |
| **Code modifiable en prod ?** | Non, copié dans l'image Docker |

---

## Commandes Utiles

```bash
# Voir quelle config est active
docker-compose config

# Voir les variables d'environnement d'un service
docker-compose exec bot env | grep ENVIRONMENT

# Démarrer en mode détaché (background)
docker-compose up -d

# Voir les logs en temps réel
docker-compose logs -f bot

# Redémarrer un service
docker-compose restart bot

# Rebuild après changement de Dockerfile
docker-compose up -d --build bot

# Arrêter sans supprimer les volumes
docker-compose down

# Arrêter ET supprimer les volumes (⚠️ perte de données)
docker-compose down -v
```
