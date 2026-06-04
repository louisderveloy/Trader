# Volumes Docker (Développement)

Ce dossier contient les **données persistantes** des services Docker en mode développement.

## Structure

```
volumes/
├── postgres/    → Base de données PostgreSQL + TimescaleDB
├── redis/       → Données Redis (pub/sub + cache)
├── grafana/     → Configuration et dashboards Grafana
├── traefik/     → Certificats HTTPS (Let's Encrypt ou mkcert)
└── bot_logs/    → Logs du bot de trading
```

## Important

- ✅ Ces dossiers sont **ignorés par git** (voir `.gitignore`)
- ✅ Les données sont **persistantes** entre les redémarrages Docker
- ⚠️ **Supprimer ces dossiers = perte de données**

## Pourquoi des volumes locaux ?

En développement, utiliser des volumes locaux (`./volumes/`) plutôt que des volumes Docker permet de :

1. **Voir les données** directement dans l'explorateur de fichiers
2. **Backup facile** : copier le dossier suffit
3. **Debug** : inspecter les fichiers de base de données si nécessaire
4. **Nettoyer facilement** : `rm -rf volumes/postgres` pour repartir de zéro

## En Production

En production, nous utilisons des **Docker named volumes** au lieu de bind mounts. Voir `docker-compose.prod.yml`.

## Commandes Utiles

### Nettoyer toutes les données (⚠️ perte de données)

```bash
# Arrêter les services
docker-compose down

# Supprimer tous les volumes
rm -rf volumes/*

# Recréer la structure
mkdir -p volumes/postgres volumes/redis volumes/grafana volumes/traefik volumes/bot_logs

# Redémarrer
docker-compose up -d
```

### Backup manuel

```bash
# Backup PostgreSQL
tar czf backup-postgres-$(date +%Y%m%d).tar.gz volumes/postgres/

# Backup tout
tar czf backup-all-volumes-$(date +%Y%m%d).tar.gz volumes/
```

### Restaurer un backup

```bash
# Arrêter les services
docker-compose down

# Supprimer les anciennes données
rm -rf volumes/postgres/

# Restaurer
tar xzf backup-postgres-20241231.tar.gz

# Redémarrer
docker-compose up -d
```

## Plus d'Infos

Voir `/docs/DOCKER_ENV_GUIDE.md` pour comprendre la différence entre dev et prod.
