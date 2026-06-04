# Notes de Configuration Windows

## Problème Résolu : PostgreSQL + Bind Mounts sur Windows

### Symptôme
```
initdb: error: could not change permissions of directory
"/var/lib/postgresql/data": Operation not permitted
```

### Cause
Sur Windows, PostgreSQL ne peut pas modifier les permissions des **bind mounts** (`./volumes/postgres`) car :
- Windows ne gère pas correctement les permissions Linux
- Le container PostgreSQL tourne avec l'user `postgres` (UID 999)
- Les fichiers créés par Windows ont des permissions incompatibles

### Solution Appliquée

**Utiliser un Docker Named Volume pour PostgreSQL uniquement**

```yaml
# docker-compose.yml
volumes:
  postgres_data:  # Named volume géré par Docker

services:
  postgres:
    volumes:
      - postgres_data:/var/lib/postgresql/data  # Au lieu de ./volumes/postgres
```

**Résultat :**
- ✅ PostgreSQL fonctionne correctement
- ✅ TimescaleDB activé et opérationnel
- ✅ Autres services gardent les bind mounts (Redis, Grafana, logs)

### Solutions Alternatives Testées

| Solution | Résultat | Note |
|----------|----------|------|
| `userns_mode: "host"` | ❌ Échec | Recommandé dans l'issue GitHub mais ne fonctionne pas sur Windows |
| Bind mount avec permissions | ❌ Échec | Windows ne supporte pas chmod/chown correctement |
| Named volume | ✅ **Fonctionne** | Solution recommandée pour Windows |

### Références
- Issue GitHub: https://github.com/timescale/timescaledb-docker-ha/issues/460
- Documentation Docker: https://docs.docker.com/storage/volumes/

---

## Configuration Actuelle

### Volumes en Développement

| Service | Type Volume | Localisation |
|---------|-------------|--------------|
| **PostgreSQL** | Named Volume | Géré par Docker (`trader_postgres_data`) |
| **Redis** | Bind Mount | `./volumes/redis/` |
| **Grafana** | Bind Mount | `./volumes/grafana/` |
| **Traefik** | Bind Mount | `./volumes/traefik/` |
| **Bot Logs** | Bind Mount | `./volumes/bot_logs/` |

### Commandes Utiles

**Voir les volumes Docker:**
```bash
docker volume ls
```

**Inspecter le volume PostgreSQL:**
```bash
docker volume inspect trader_postgres_data
```

**Backup PostgreSQL (Windows):**
```bash
# Dump SQL
docker exec trader-postgres pg_dump -U trader trader_bot | gzip > backup.sql.gz

# Ou backup du volume
docker run --rm -v trader_postgres_data:/data -v G:/backups:/backup alpine tar czf /backup/postgres-backup.tar.gz -C /data .
```

**Restaurer PostgreSQL:**
```bash
# Depuis dump SQL
gunzip -c backup.sql.gz | docker exec -i trader-postgres psql -U trader -d trader_bot

# Depuis volume backup
docker run --rm -v trader_postgres_data:/data -v G:/backups:/backup alpine tar xzf /backup/postgres-backup.tar.gz -C /data
```

**Nettoyer le volume PostgreSQL (⚠️ perte de données):**
```bash
docker-compose down
docker volume rm trader_postgres_data
docker-compose up -d postgres
```

---

## Statut des Services

### ✅ Services Fonctionnels

1. **PostgreSQL + TimescaleDB**
   - Status: Healthy
   - Version: PostgreSQL 16.14 + TimescaleDB 2.27.2
   - Port: 5432
   - Volume: `trader_postgres_data` (named volume)

2. **Redis**
   - Status: Healthy
   - Version: 7.4.9
   - Port: 6379
   - Volume: `./volumes/redis/` (bind mount)

3. **Traefik**
   - Status: Running
   - Dashboard: http://localhost:8080
   - Ports: 80, 443, 8080

4. **Grafana**
   - Status: Running
   - Port: 3000
   - URL: http://grafana.localhost (via Traefik)
   - Volume: `./volumes/grafana/` (bind mount)

### ⏳ Services en Attente de Code

Ces services **crashent actuellement** car le code n'existe pas encore (normal en Phase 0) :

- **Bot** - Redémarre en boucle (pas de code Python)
- **API** - Redémarre en boucle (pas de code FastAPI)
- **Dashboard** - Redémarre en boucle (pas de code Vue.js)

**Ils seront implémentés dans les phases suivantes.**

---

## Tests de Validation

### Test 1 : PostgreSQL
```bash
docker exec trader-postgres psql -U trader -d trader_bot -c "SELECT version();"
# ✅ Devrait afficher PostgreSQL 16.14
```

### Test 2 : TimescaleDB
```bash
docker exec trader-postgres psql -U trader -d trader_bot -c "\dx"
# ✅ Devrait afficher timescaledb 2.27.2
```

### Test 3 : Redis
```bash
docker exec trader-redis redis-cli PING
# ✅ Devrait répondre PONG
```

### Test 4 : Traefik Dashboard
```
Navigateur: http://localhost:8080
# ✅ Devrait afficher le dashboard Traefik
```

### Test 5 : Grafana
```
Navigateur: http://grafana.localhost
# ✅ Devrait afficher la page de login Grafana
# Login: admin / admin (à changer)
```

---

## Prochaines Étapes

Phase 0 est **complète** avec les ajustements Windows. Prochaines phases :

1. **Phase 1** : Créer le schéma de base de données (migrations Alembic)
2. **Phase 2** : Implémenter le connecteur Binance
3. **Phase 3** : Créer les indicateurs techniques
4. ... (voir CLAUDE.md)

---

## Notes Importantes

### Différences Dev vs Prod

| Aspect | Dev (Windows) | Prod (Linux VPS) |
|--------|---------------|------------------|
| PostgreSQL | Named volume | Named volume |
| Autres services | Bind mounts | Named volumes |
| Permissions | Gérées par Docker | Correctes nativement |

En production sur Linux, vous **pouvez** utiliser des bind mounts pour PostgreSQL si vous le souhaitez, car Linux gère correctement les permissions.

### Avertissements

- ⚠️ Le dossier `./volumes/postgres/` existe mais est **vide** (normal)
- ⚠️ Les données PostgreSQL sont dans un volume Docker, pas visible directement
- ⚠️ Pour backup PostgreSQL, utilisez `pg_dump` ou `docker volume backup`
- ⚠️ Les services bot/api/dashboard crashent en Phase 0 (normal, pas de code)

---

## Support

Si vous rencontrez des problèmes :

1. Vérifier les logs : `docker-compose logs <service>`
2. Vérifier le status : `docker-compose ps`
3. Consulter `/docs/DOCKER_ENV_GUIDE.md`
4. Consulter `/docs/A6_runbook.md`
