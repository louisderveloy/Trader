# A5 — Migration Auth : Option A → Option B

## Vue d'ensemble

Procédure pour migrer de l'architecture auth actuelle (Option A) vers l'architecture multi-comptes Grafana (Option B).

---

## Architecture Actuelle (Option A)

```
┌──────────┐
│Navigateur│
└────┬─────┘
     │
     ▼
┌────────────────┐
│ Traefik        │
│ ForwardAuth    │  ←─── Vérifie JWT
│ (vérifie JWT)  │
└────┬───────────┘
     │
     ├────→ Dashboard Vue.js
     ├────→ API FastAPI
     └────→ Grafana (mode anonyme)
```

**Caractéristiques :**
- Un seul login pour tout
- JWT généré par FastAPI au login
- Grafana en mode anonyme (pas de gestion d'utilisateurs)
- Tous les utilisateurs Grafana = Admin (mono-user v1)

---

## Architecture Cible (Option B)

```
┌──────────┐
│Navigateur│
└────┬─────┘
     │
     ▼
┌────────────────────────┐
│ Traefik ForwardAuth    │  ←─── Vérifie JWT
│ + injecte header       │       Injecte X-Webauth-User
│ X-Webauth-User         │
└────┬───────────────────┘
     │
     ├────→ Dashboard Vue.js
     ├────→ API FastAPI
     └────→ Grafana (auth proxy mode)
              ↓
         Lit X-Webauth-User
         Crée/connecte utilisateur automatiquement
```

**Caractéristiques :**
- Un seul login pour tout (conservé)
- JWT généré par FastAPI au login (conservé)
- Grafana lit le header `X-Webauth-User` et gère automatiquement les utilisateurs
- Utilisateurs Grafana mappés sur les utilisateurs de la table `users`
- Support multi-utilisateurs avec rôles distincts

---

## Étapes de Migration

### Étape 1 : Préparation de la base de données

#### 1.1 Ajouter colonnes Grafana à la table `users`

```sql
-- Migration Alembic
ALTER TABLE users ADD COLUMN grafana_org_id INTEGER;
ALTER TABLE users ADD COLUMN grafana_role VARCHAR(20) DEFAULT 'Viewer';

-- Valeurs possibles pour grafana_role : 'Admin', 'Editor', 'Viewer'
```

#### 1.2 Créer un utilisateur admin par défaut

```sql
INSERT INTO users (username, email, hashed_password, is_active, is_admin, grafana_role)
VALUES (
    'admin',
    'admin@localhost',
    '$2b$12$...', -- hash bcrypt du mot de passe
    true,
    true,
    'Admin'
);
```

---

### Étape 2 : Configuration Grafana (Auth Proxy)

#### 2.1 Modifier `docker-compose.yml`

```yaml
grafana:
  environment:
    # Désactiver l'auth anonyme
    GF_AUTH_ANONYMOUS_ENABLED: false

    # Activer l'auth proxy
    GF_AUTH_PROXY_ENABLED: true
    GF_AUTH_PROXY_HEADER_NAME: X-Webauth-User
    GF_AUTH_PROXY_HEADER_PROPERTY: username
    GF_AUTH_PROXY_AUTO_SIGN_UP: true
    GF_AUTH_PROXY_SYNC_TTL: 60

    # Activer les organisations
    GF_USERS_AUTO_ASSIGN_ORG: true
    GF_USERS_AUTO_ASSIGN_ORG_ROLE: Viewer

    # Désactiver l'inscription directe
    GF_USERS_ALLOW_SIGN_UP: false
```

#### 2.2 Configuration avancée (optionnel)

Pour mapper les rôles via le header :

```yaml
grafana:
  environment:
    # Mapper le rôle depuis un header additionnel
    GF_AUTH_PROXY_HEADERS: "Role:X-Webauth-Role"
```

---

### Étape 3 : Middleware Traefik ForwardAuth (injection header)

#### 3.1 Créer un service ForwardAuth personnalisé

Créer `/api/auth/forward_auth.py` :

```python
from fastapi import Request, HTTPException, status
from fastapi.responses import Response
import jwt

async def forward_auth_middleware(request: Request) -> Response:
    """
    Middleware ForwardAuth pour Traefik.
    Vérifie le JWT et injecte les headers X-Webauth-*.
    """
    # Extraire le token JWT du cookie ou header Authorization
    token = request.cookies.get("access_token") or \
            request.headers.get("Authorization", "").replace("Bearer ", "")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        # Décoder le JWT
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role", "Viewer")  # Grafana role

        # Créer la réponse avec les headers injectés
        response = Response(status_code=200)
        response.headers["X-Webauth-User"] = username
        response.headers["X-Webauth-Role"] = role
        return response

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
```

#### 3.2 Ajouter une route ForwardAuth dans l'API

```python
# api/main.py
from fastapi import FastAPI
from api.auth.forward_auth import forward_auth_middleware

app = FastAPI()

@app.get("/auth/verify")
async def verify_auth(request: Request):
    """Route ForwardAuth pour Traefik"""
    return await forward_auth_middleware(request)
```

#### 3.3 Configurer Traefik pour utiliser ForwardAuth

```yaml
# docker-compose.yml
traefik:
  command:
    # ... autres commandes
    - "--entrypoints.websecure.http.middlewares=forward-auth"

# Labels pour le middleware ForwardAuth
labels:
  - "traefik.http.middlewares.forward-auth.forwardauth.address=http://api:8000/auth/verify"
  - "traefik.http.middlewares.forward-auth.forwardauth.authResponseHeaders=X-Webauth-User,X-Webauth-Role"
  - "traefik.http.middlewares.forward-auth.forwardauth.trustForwardHeader=true"

# Appliquer le middleware aux routes protégées
dashboard:
  labels:
    - "traefik.http.routers.dashboard.middlewares=forward-auth"

grafana:
  labels:
    - "traefik.http.routers.grafana.middlewares=forward-auth"
```

---

### Étape 4 : Modifier l'API pour inclure le rôle Grafana dans le JWT

#### 4.1 Ajouter le rôle Grafana au payload JWT

```python
# api/auth/jwt.py
def create_access_token(user: User) -> str:
    payload = {
        "sub": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "role": user.grafana_role,  # Nouveau: rôle Grafana
        "exp": datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token
```

---

### Étape 5 : Synchronisation utilisateurs Grafana

#### 5.1 Endpoint pour synchroniser les utilisateurs

Créer un endpoint API pour synchroniser manuellement les utilisateurs si nécessaire :

```python
# api/admin/sync_grafana.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.post("/admin/sync-grafana-users")
async def sync_grafana_users(db: AsyncSession = Depends(get_db)):
    """
    Synchronise tous les utilisateurs de la DB vers Grafana.
    À exécuter après la migration.
    """
    # Récupérer tous les utilisateurs
    users = await db.execute(select(User).where(User.is_active == True))
    users = users.scalars().all()

    # Pour chaque utilisateur, simuler une connexion à Grafana
    # (Grafana créera automatiquement l'utilisateur via auth proxy)
    for user in users:
        # Logique de synchronisation si nécessaire
        pass

    return {"synced_users": len(users)}
```

---

### Étape 6 : Tests de migration

#### 6.1 Plan de test

1. **Test de login** : Vérifier que le login fonctionne et génère un JWT avec le rôle
2. **Test Grafana** : Accéder à Grafana et vérifier que l'utilisateur est créé automatiquement
3. **Test de rôles** : Vérifier que les rôles Admin/Editor/Viewer sont correctement appliqués
4. **Test de déconnexion** : Vérifier que la déconnexion fonctionne sur tous les services
5. **Test multi-utilisateurs** : Créer plusieurs utilisateurs et vérifier l'isolation des données

#### 6.2 Rollback plan

En cas de problème, revenir à l'Option A :

```yaml
# docker-compose.yml
grafana:
  environment:
    GF_AUTH_PROXY_ENABLED: false
    GF_AUTH_ANONYMOUS_ENABLED: true
    GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
```

Retirer les labels `forward-auth` de Traefik.

---

## Avantages de l'Option B

1. **Multi-utilisateurs** : Support de plusieurs utilisateurs avec rôles distincts
2. **Isolation** : Possibilité de créer des organisations Grafana séparées
3. **Audit** : Traçabilité des actions par utilisateur dans Grafana
4. **Sécurité** : Contrôle d'accès granulaire (Admin/Editor/Viewer)

---

## Inconvénients de l'Option B

1. **Complexité** : Architecture plus complexe à maintenir
2. **Débogage** : Plus de points de défaillance potentiels
3. **Performance** : Légère surcharge due aux appels ForwardAuth

---

## Recommandation

- **v1 (mono-utilisateur)** : Rester sur Option A (plus simple)
- **v2 (multi-utilisateurs)** : Migrer vers Option B

---

## Timeline de Migration

| Étape | Durée estimée | Risque |
|-------|---------------|--------|
| Préparation DB | 1h | Faible |
| Config Grafana | 1h | Moyen |
| Middleware ForwardAuth | 2h | Moyen |
| Modification API JWT | 1h | Faible |
| Tests | 2h | — |
| **Total** | **7h** | — |

---

## Support et Troubleshooting

### Logs à surveiller

```bash
# Traefik
docker logs trader-traefik

# API (ForwardAuth)
docker logs trader-api

# Grafana
docker logs trader-grafana
```

### Headers de debug

Pour débugger, ajouter un endpoint de test qui affiche les headers reçus :

```python
@app.get("/debug/headers")
async def debug_headers(request: Request):
    return dict(request.headers)
```
