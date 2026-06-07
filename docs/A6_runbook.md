# A6 — Runbook Opérationnel

## Vue d'ensemble

Procédures opérationnelles pour la maintenance et le dépannage du bot de trading.

---

## Démarrage des Services

### Développement Local

```bash
# Démarrer tous les services
docker-compose up -d

# Vérifier le statut
docker-compose ps

# Voir les logs
docker-compose logs -f

# Voir les logs d'un service spécifique
docker-compose logs -f bot
docker-compose logs -f api
```

### Production

```bash
# Démarrer avec le fichier de prod
docker-compose -f docker-compose.prod.yml up -d

# Vérifier le statut
docker-compose -f docker-compose.prod.yml ps

# Voir les logs (dernières 100 lignes)
docker-compose -f docker-compose.prod.yml logs --tail=100 -f
```

---

## Arrêt des Services

### Arrêt gracieux (recommandé)

```bash
# Dev
docker-compose stop

# Prod
docker-compose -f docker-compose.prod.yml stop
```

Le bot terminera les trades en cours avant de s'arrêter.

### Arrêt forcé (urgence uniquement)

```bash
# Dev
docker-compose down

# Prod
docker-compose -f docker-compose.prod.yml down
```

⚠️ **Attention** : Les positions ouvertes ne seront pas fermées automatiquement.

---

## Redémarrage du Bot

### Redémarrage standard

```bash
# Dev
docker-compose restart bot

# Prod
docker-compose -f docker-compose.prod.yml restart bot
```

### Redémarrage après modification de code

```bash
# Dev (avec watch activé, le redémarrage est automatique)
# Sinon :
docker-compose up -d --build bot

# Prod
docker-compose -f docker-compose.prod.yml up -d --build bot
```

---

## Gestion des Positions Ouvertes

### Vérifier les positions ouvertes

```bash
# Via l'API
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://api.yourdomain.com/trades/open

# Via psql
docker exec -it trader-postgres psql -U trader -d trader_bot -c \
  "SELECT * FROM trades WHERE exit_order_id IS NULL;"
```

### Fermer manuellement une position

```bash
# Via le dashboard Vue.js
# Page Trades > Bouton "Fermer position"

# Via l'API
curl -X POST -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://api.yourdomain.com/trades/{trade_id}/close
```

### Procédure d'urgence (Kill Switch)

En cas d'urgence, fermer toutes les positions immédiatement :

```bash
# Via l'API (endpoint kill switch)
curl -X POST -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://api.yourdomain.com/emergency/close-all-positions
```

⚠️ **Note** : Cette action ferme toutes les positions au prix market. À utiliser uniquement en cas d'urgence.

---

## Backup de la Base de Données

### Backup manuel

```bash
# Créer un backup complet
docker exec trader-postgres pg_dump -U trader trader_bot | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Créer un backup schema-only (pour tests)
docker exec trader-postgres pg_dump -U trader -s trader_bot | gzip > schema_$(date +%Y%m%d).sql.gz
```

### Backup automatique (cron)

Ajouter dans la crontab du VPS :

```bash
# Ouvrir la crontab
crontab -e

# Ajouter une ligne pour backup quotidien à 3h du matin
0 3 * * * /usr/bin/docker exec trader-postgres pg_dump -U trader trader_bot | gzip > /backups/trader_bot_$(date +\%Y\%m\%d).sql.gz

# Garder seulement les 30 derniers jours
0 4 * * * find /backups -name "trader_bot_*.sql.gz" -mtime +30 -delete
```

### Restauration depuis un backup

```bash
# Arrêter le bot
docker-compose stop bot

# Restaurer le backup
gunzip -c backup_20241231_150000.sql.gz | docker exec -i trader-postgres psql -U trader -d trader_bot

# Redémarrer le bot
docker-compose start bot
```

---

## Rollback de Configuration

### Principe

Toute modification de configuration crée un nouveau `run_id` avec snapshot. Le rollback consiste à réactiver un snapshot précédent.

### Procédure de rollback

#### Via le dashboard

1. Page Configuration > Historique
2. Sélectionner le snapshot à restaurer
3. Cliquer sur "Restaurer cette configuration"
4. Confirmer

#### Via l'API

```bash
curl -X POST -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://api.yourdomain.com/config/rollback \
  -d '{"run_id": "uuid-of-previous-run"}'
```

#### Via la base de données (manuel)

```sql
-- Récupérer le snapshot de configuration d'un run précédent
SELECT config_snapshot FROM runs WHERE id = 'uuid-of-previous-run';

-- Créer un nouveau run avec cette configuration
-- (via l'API de préférence, pas de manipulation manuelle)
```

---

## Monitoring et Alertes

### Healthchecks

```bash
# Vérifier que tous les services sont healthy
docker ps --filter "health=healthy"

# Si un service est unhealthy, voir les logs
docker inspect --format='{{json .State.Health}}' trader-bot | jq
```

### Métriques clés à surveiller

| Métrique | Seuil d'alerte | Action |
|----------|----------------|--------|
| Erreurs/minute | > 5 | Vérifier logs d'erreur |
| Latence API | > 2s | Vérifier charge serveur |
| Connexion Bybit | Perdue > 5min | Redémarrer bot |
| Ordres rejetés | > 3 consécutifs | Vérifier solde et config |
| Drawdown | > 20% | Arrêter le bot, analyser |

### Logs d'erreurs

```bash
# Afficher les erreurs des dernières 24h
docker exec trader-postgres psql -U trader -d trader_bot -c \
  "SELECT * FROM errors_log WHERE occurred_at > NOW() - INTERVAL '24 hours' ORDER BY occurred_at DESC;"
```

---

## Gestion des Secrets

### Rotation des secrets

#### Bybit API Keys

```bash
# 1. Générer de nouvelles clés sur Bybit
# 2. Mettre à jour le fichier .env
vim .env
# Modifier BYBIT_MAINNET_API_KEY et BYBIT_MAINNET_API_SECRET

# 3. Redémarrer le bot
docker-compose restart bot
```

#### JWT Secret

```bash
# 1. Générer un nouveau secret
openssl rand -hex 32

# 2. Mettre à jour .env
vim .env
# Modifier JWT_SECRET_KEY

# 3. Redémarrer l'API (invalide tous les tokens existants)
docker-compose restart api

# 4. Les utilisateurs devront se reconnecter
```

#### PostgreSQL Password

```bash
# 1. Se connecter à PostgreSQL
docker exec -it trader-postgres psql -U trader

# 2. Changer le mot de passe
ALTER USER trader WITH PASSWORD 'new_password';

# 3. Mettre à jour .env
vim .env
# Modifier POSTGRES_PASSWORD

# 4. Redémarrer tous les services
docker-compose down
docker-compose up -d
```

---

## Configuration Firewall PostgreSQL (Production)

### Contexte

En production, PostgreSQL est exposé sur `127.0.0.1:5432` (localhost uniquement) pour des raisons de sécurité.
Pour permettre à un serveur Grafana externe de se connecter, il faut configurer le firewall (ufw) pour autoriser UNIQUEMENT l'adresse IP du serveur Grafana.

### Configuration initiale du firewall

```bash
# Installer ufw si nécessaire
sudo apt-get update
sudo apt-get install ufw

# Activer ufw au démarrage
sudo systemctl enable ufw

# Autoriser SSH (IMPORTANT: à faire AVANT d'activer ufw)
sudo ufw allow 22/tcp
```

### Autoriser uniquement le serveur Grafana

```bash
# Remplacer <grafana-ip> par l'adresse IP réelle du serveur Grafana
sudo ufw allow from <grafana-ip> to any port 5432 comment 'Grafana PostgreSQL access'

# Bloquer tout autre accès au port 5432
sudo ufw deny 5432 comment 'Block all other PostgreSQL access'

# Activer le firewall
sudo ufw enable
```

### Vérifier la configuration

```bash
# Afficher toutes les règles
sudo ufw status numbered

# Exemple de sortie attendue:
#      To                         Action      From
#      --                         ------      ----
# [ 1] 22/tcp                     ALLOW IN    Anywhere
# [ 2] 5432                       ALLOW IN    <grafana-ip>              # Grafana PostgreSQL access
# [ 3] 5432                       DENY IN     Anywhere                  # Block all other PostgreSQL access
```

### Tester la connexion depuis Grafana

Depuis le serveur Grafana :

```bash
# Tester la connexion PostgreSQL
psql -h <your-server-ip> -p 5432 -U trader -d trader_bot

# Devrait demander le mot de passe et se connecter avec succès
```

Depuis un autre serveur (non autorisé) :

```bash
# Cette commande devrait échouer (connection refused / timeout)
psql -h <your-server-ip> -p 5432 -U trader -d trader_bot
```

### Modifier la liste des IPs autorisées

```bash
# Supprimer l'ancienne règle (utiliser le numéro de la règle)
sudo ufw status numbered
sudo ufw delete 2  # Numéro de la règle Grafana

# Ajouter la nouvelle IP
sudo ufw allow from <nouvelle-grafana-ip> to any port 5432 comment 'Grafana PostgreSQL access'

# Recharger le firewall
sudo ufw reload
```

### Désactiver temporairement le firewall (DEBUG UNIQUEMENT)

```bash
# ATTENTION: Désactive toute protection firewall
sudo ufw disable

# Pour réactiver après debug
sudo ufw enable
```

### Logs du firewall

```bash
# Activer les logs ufw
sudo ufw logging on

# Voir les logs
sudo tail -f /var/log/ufw.log

# Logs des tentatives de connexion bloquées sur port 5432
sudo grep "DPT=5432" /var/log/ufw.log
```

### Règles supplémentaires pour production

```bash
# Autoriser HTTP/HTTPS pour Traefik
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'

# Bloquer tous les autres ports par défaut
sudo ufw default deny incoming
sudo ufw default allow outgoing
```

### Checklist configuration firewall

- [ ] SSH (port 22) autorisé AVANT d'activer ufw
- [ ] IP du serveur Grafana autorisée sur port 5432
- [ ] Tous les autres accès au port 5432 bloqués
- [ ] HTTP (80) et HTTPS (443) autorisés pour Traefik
- [ ] Firewall activé et persistant au redémarrage
- [ ] Configuration testée depuis le serveur Grafana
- [ ] Configuration testée depuis un serveur non autorisé (doit échouer)

---

## Réponse aux Incidents de Sécurité

### Suspicion de Compromission

En cas de suspicion de compromission (accès non autorisé, comportement anormal, tentatives de connexion suspectes) :

#### Actions immédiates

```bash
# 1. Arrêter le bot (stoppe le trading)
docker-compose -f docker-compose.prod.yml stop bot

# 2. Vérifier les logs d'authentification récents
docker logs trader-api | grep -i "failed login\|unauthorized" | tail -100

# 3. Vérifier les erreurs récentes en base de données
docker exec trader-postgres psql -U trader -d trader_bot -c \
  "SELECT * FROM errors_log WHERE occurred_at > NOW() - INTERVAL '24 hours' ORDER BY occurred_at DESC LIMIT 50;"

# 4. Vérifier les trades récents pour détecter toute activité anormale
docker exec trader-postgres psql -U trader -d trader_bot -c \
  "SELECT * FROM trades WHERE created_at > NOW() - INTERVAL '24 hours' ORDER BY created_at DESC;"
```

#### Rotation des secrets

Si une compromission est confirmée ou suspectée :

```bash
# 1. Générer de nouveaux secrets
openssl rand -hex 32 > jwt_secret.txt
openssl rand -base64 24 > db_password.txt
cat jwt_secret.txt
cat db_password.txt

# 2. Mettre à jour le fichier .env
vim .env
# Modifier JWT_SECRET_KEY et POSTGRES_PASSWORD

# 3. Changer le mot de passe PostgreSQL
docker exec -it trader-postgres psql -U trader -d trader_bot
# Dans psql :
ALTER USER trader WITH PASSWORD '<nouveau_mot_de_passe>';
\q

# 4. Redémarrer tous les services (invalide toutes les sessions)
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# 5. Vérifier que les services redémarrent correctement
docker-compose -f docker-compose.prod.yml logs -f

# 6. Se reconnecter au dashboard avec les nouvelles credentials
```

#### Vérification de l'intégrité

```bash
# Vérifier qu'il n'y a pas de modifications non autorisées du code
git status
git diff

# Vérifier les conteneurs en cours d'exécution
docker ps -a

# Vérifier les connexions réseau actives
docker exec trader-api netstat -tuln

# Vérifier les règles firewall
sudo ufw status numbered
```

### Tentatives de Connexion Suspectes

Si le rate limiting bloque de nombreuses tentatives :

```bash
# Voir les tentatives de connexion bloquées (rate limit exceeded)
docker logs trader-api | grep -i "rate limit exceeded\|429" | tail -50

# Identifier les IPs sources
docker logs trader-api | grep "Failed login" | awk '{print $NF}' | sort | uniq -c | sort -nr

# Si nécessaire, bloquer une IP spécifique via le firewall
sudo ufw deny from <ip-malveillante>
```

### Audit de Sécurité Régulier

Commandes à exécuter régulièrement (hebdomadaire recommandé) :

```bash
# 1. Vérifier les dépendances vulnérables (Python)
cd /path/to/trader
source venv/bin/activate  # Si environnement virtuel
pip-audit

# 2. Vérifier les dépendances vulnérables (Node.js)
cd dashboard
npm audit

# 3. Vérifier les règles firewall
sudo ufw status verbose

# 4. Vérifier les logs d'erreurs récents
docker-compose -f docker-compose.prod.yml logs --tail=100 | grep -i "error\|critical"

# 5. Vérifier que les secrets n'ont pas été commités par erreur
git log -p | grep -i "jwt_secret\|postgres_password\|api_key"
```

### Réinitialisation Admin Password

**Note**: L'authentification actuelle utilise un mot de passe en clair (phase de test uniquement).
Migration vers Authelia prévue pour la production.

```bash
# Phase actuelle (mot de passe en clair)
# 1. Modifier .env
vim .env
# Changer ADMIN_PASSWORD=nouveau_mot_de_passe

# 2. Redémarrer l'API
docker-compose -f docker-compose.prod.yml restart api

# Phase future (après migration Authelia)
# Utiliser le flow de réinitialisation Authelia
```

### Sauvegarde d'Urgence

En cas d'incident critique, créer immédiatement un backup complet :

```bash
# Backup complet de la base de données
docker exec trader-postgres pg_dump -U trader trader_bot | gzip > emergency_backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Copier les logs actuels
docker-compose -f docker-compose.prod.yml logs --no-color > logs_$(date +%Y%m%d_%H%M%S).txt

# Backup de la configuration
cp .env .env.backup_$(date +%Y%m%d_%H%M%S)
```

### Restauration depuis un Backup

Si les données ont été compromises :

```bash
# 1. Arrêter le bot
docker-compose -f docker-compose.prod.yml stop bot

# 2. Restaurer le backup
gunzip -c emergency_backup_20241231_150000.sql.gz | \
  docker exec -i trader-postgres psql -U trader -d trader_bot

# 3. Vérifier l'intégrité des données restaurées
docker exec trader-postgres psql -U trader -d trader_bot -c \
  "SELECT COUNT(*) FROM trades; SELECT COUNT(*) FROM orders;"

# 4. Redémarrer le bot
docker-compose -f docker-compose.prod.yml start bot
```

### Contact en Cas d'Urgence

- **Binance Support** : https://www.binance.com/en/support
- **Logs à collecter** : API logs, error logs, firewall logs (`/var/log/ufw.log`)

---

## Mise à Jour du Code

### Déploiement continu (recommandé)

```bash
# Sur le VPS
cd /path/to/trader

# Pull les dernières modifications
git pull origin main

# Rebuild et redémarrer les services
docker-compose -f docker-compose.prod.yml up -d --build

# Vérifier les logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Mise à jour avec downtime minimal

```bash
# 1. Arrêter uniquement le bot (garder API et dashboard actifs)
docker-compose stop bot

# 2. Pull et rebuild
git pull origin main
docker-compose build bot

# 3. Redémarrer le bot
docker-compose up -d bot

# 4. Vérifier
docker-compose logs -f bot
```

---

## Migrations de Base de Données

### Appliquer une nouvelle migration

```bash
# Dev
docker-compose exec bot alembic upgrade head

# Prod
docker-compose -f docker-compose.prod.yml exec bot alembic upgrade head
```

### Rollback d'une migration

```bash
# Rollback d'une révision
docker-compose exec bot alembic downgrade -1

# Rollback à une révision spécifique
docker-compose exec bot alembic downgrade <revision_id>
```

### Créer une nouvelle migration

```bash
# Auto-générer depuis les modèles SQLAlchemy
docker-compose exec bot alembic revision --autogenerate -m "description"

# Créer une migration vide
docker-compose exec bot alembic revision -m "description"

# Éditer le fichier de migration
vim db/migrations/versions/<revision>_description.py
```

---

## Résolution de Problèmes

### Le bot ne démarre pas

```bash
# Vérifier les logs
docker-compose logs bot

# Problèmes communs :
# - Connexion DB échouée → Vérifier DATABASE_URL dans .env
# - Connexion Redis échouée → Vérifier que Redis est démarré
# - Erreur d'import Python → Rebuild l'image : docker-compose build bot
```

### Ordres rejetés

```bash
# Vérifier le solde sur Bybit
# Via l'API Bybit ou le dashboard

# Vérifier les logs d'erreur
docker-compose logs bot | grep "OrderRejected"

# Causes communes :
# - Solde insuffisant
# - Taille de position trop petite (min 0.001 BTC sur Bybit)
# - API keys invalides
# - Bybit maintenance
```

### API lente

```bash
# Vérifier la charge CPU/RAM
docker stats

# Vérifier les connexions DB
docker exec trader-postgres psql -U trader -d trader_bot -c \
  "SELECT count(*) FROM pg_stat_activity;"

# Vérifier les slow queries
docker exec trader-postgres psql -U trader -d trader_bot -c \
  "SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
```

### Grafana inaccessible

```bash
# Vérifier que Grafana est démarré
docker-compose ps grafana

# Vérifier les logs
docker-compose logs grafana

# Vérifier la configuration Traefik
docker-compose logs traefik | grep grafana

# Tester directement (sans Traefik)
curl http://localhost:3000
```

---

## Réconciliation des Positions (Exchange vs DB)

### Vérification manuelle

```bash
# Positions ouvertes dans la DB
docker exec trader-postgres psql -U trader -d trader_bot -c \
  "SELECT * FROM orders WHERE status = 'filled' AND id NOT IN (SELECT entry_order_id FROM trades UNION SELECT exit_order_id FROM trades);"

# Comparer avec les positions sur Bybit
# Via le dashboard Bybit ou l'API
```

### Script de réconciliation

```bash
# Exécuter le script de réconciliation
docker-compose exec bot python scripts/reconcile_positions.py

# Le script doit :
# - Lister les positions ouvertes sur Bybit
# - Lister les trades non fermés dans la DB
# - Rapporter les divergences
```

---

## Contacts et Escalade

### Support Bybit

- **Testnet** : https://testnet.bybit.com/en-US/help-center
- **Mainnet** : https://www.bybit.com/en-US/help-center

### Logs à collecter pour le debug

```bash
# Créer un bundle de debug
./scripts/create_debug_bundle.sh

# Contient :
# - Logs des 24 dernières heures
# - État des services (docker ps)
# - Configuration (sans secrets)
# - Dernières erreurs en DB
```

---

## Annexes

### Checklist avant passage en production

- [ ] Backups automatiques configurés
- [ ] Monitoring configuré (Grafana alertes)
- [ ] Secrets changés (pas de valeurs par défaut)
- [ ] Bybit API keys en mainnet
- [ ] Tests sur testnet pendant au moins 4 semaines
- [ ] Procédure kill switch testée
- [ ] Discord notifications configurées
- [ ] Firewall VPS configuré
- [ ] HTTPS Let's Encrypt actif
- [ ] Logs rotationnés (logrotate)

### Commandes utiles

```bash
# Redémarrer uniquement Redis
docker-compose restart redis

# Voir l'utilisation disque
docker system df

# Nettoyer les images inutilisées
docker system prune -a

# Exporter les métriques de performance
docker-compose exec bot python scripts/export_metrics.py --start 2024-01-01 --end 2024-12-31
```
