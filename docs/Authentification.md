# Authentification & Autorisation

> Document de référence sur la façon dont le projet gère l'authentification (qui es-tu ?) et
> l'autorisation (as-tu le droit ?). Le plan d'implémentation et le suivi des tâches sont dans
> `.agent/authelia-implementation.md` ; l'audit de sécurité dans `.agent/security-review.md`.
>
> ⚠️ Ce document **remplace** le schéma ForwardAuth décrit dans `docs/A5_auth_migration.md` (Grafana est
> désormais hébergé séparément et n'est plus protégé par l'API).

---

## 1. Vue d'ensemble

L'authentification repose sur **Authelia** comme fournisseur **OpenID Connect (OIDC)** en **production**,
et sur un login local (mot de passe) **en développement uniquement**. Le choix se fait via la variable
`AUTH_MODE` :

| `AUTH_MODE`     | Environnement | Description                                                              |
|-----------------|---------------|--------------------------------------------------------------------------|
| `local`         | **dev**       | Login interne (cookie JWT). Auth réelle désactivée, rôle dérivé de `DEV_USER_GROUP`. |
| `authelia_oidc` | **prod**      | Authelia (`auth.trader.derveloy.eu`) émet l'identité ; l'API est *Relying Party* OIDC. |

**Règle stricte (sécurité) :** en production, `AUTH_MODE` **doit** valoir `authelia_oidc`. Tout
démarrage en `environment=prod` avec `AUTH_MODE=local` provoque un **échec de boot** de l'API (le
bypass de dev ne doit jamais être atteignable en prod).

### Trois niveaux d'accès (groupes Authelia)

| Groupe Authelia | Rôle interne (`Role`) | Droits                                                           |
|-----------------|-----------------------|-----------------------------------------------------------------|
| `admins`        | `ADMIN`               | Tout : lancer/arrêter des runs, sauvegarder la config, activer des poids… |
| `viewers`       | `VIEWER`              | Lecture seule : dashboard et données, **aucune action mutante**. |
| *(aucun)*       | —                     | Authentifié mais non autorisé : **aucune session**, redirigé vers `/no-access`. |

La page `/no-access` indique seulement de **contacter le propriétaire du site** (sans coordonnées).

---

## 2. Architecture : motif BFF (Backend-for-Frontend)

L'API FastAPI est un **client confidentiel OIDC** qui réalise le flux **Authorization Code + PKCE**.
Elle conserve les jetons OIDC **côté serveur** et émet sa **propre** session (cookie JWT httpOnly).
**Le SPA Vue ne voit jamais les jetons OIDC** — il ne manipule qu'un cookie de session opaque.

```
┌──────────┐   "Se connecter" (navigation pleine page)
│   SPA    │ ───────────────────────────────► API GET /auth/oidc/login
│  Vue.js  │                                      │ discovery /.well-known/openid-configuration
└──────────┘                                      │ génère state + nonce + PKCE(S256)
     ▲                                            │ écrit un cookie de transaction CHIFFRÉ
     │                                            ▼ 302
     │                                  Authelia  /authorize   (auth.trader.derveloy.eu)
     │                                            │ l'utilisateur s'authentifie
     │                                            ▼ 302
     │                                  API GET /auth/oidc/callback?code&state
     │                                      │ valide l'id_token (signature RS256, iss, aud, nonce, exp)
     │                                      │ lit la claim `groups` → mappe vers Role
     │   302 (cookie session httpOnly)      │
     └──────────────────────────────────── ┤  admin/viewer → émet session JWT (sub+role+email)
        302 /no-access (aucun cookie) ──────┘  aucun groupe → pas de session
```

**Après connexion**, chaque appel API porte le cookie de session ; l'autorisation est assurée par les
dépendances existantes `require_admin` / `require_viewer` + protection **CSRF** (double-submit). Le rôle
est **figé dans le JWT de session au moment du login** — voir §5 sur la latence de révocation.

### Pourquoi BFF (et pas de jeton dans le navigateur) ?

- Les jetons OIDC restent côté serveur → pas exposés à un éventuel XSS.
- Réutilise l'infrastructure cookie httpOnly + CSRF + gardes de rôle déjà en place : OIDC ne remplace
  que **la résolution de l'identité au login** et ajoute la ré-authentification (step-up).
- **Pas de ForwardAuth Traefik** sur l'API/dashboard : l'API-RP *est* le contrôle d'accès. Un
  ForwardAuth bloquerait le callback OIDC.

---

## 3. Flux détaillés

### 3.1 Connexion

1. Le SPA déclenche une **navigation pleine page** vers `GET /auth/oidc/login` (jamais un `fetch`/axios :
   le navigateur ne peut pas suivre la redirection cross-origin vers Authelia en XHR).
2. L'API construit l'URL d'autorisation (discovery, PKCE S256, `state`, `nonce`), stocke la transaction
   dans un **cookie chiffré** à courte durée de vie (≤5 min, usage unique), puis redirige vers Authelia.
3. L'utilisateur s'authentifie sur `auth.trader.derveloy.eu`.
4. Authelia redirige vers `GET /auth/oidc/callback` ; l'API valide l'`id_token` (§4), lit `groups`,
   mappe vers un rôle, puis :
   - **admin/viewer** : émet le cookie de session et redirige vers la page demandée (`return_to`) ;
   - **aucun groupe** : n'émet **aucune** session et redirige vers `/no-access`.

### 3.2 Déconnexion

`POST /auth/oidc/logout` efface la session ; une redirection de fin de session Authelia est optionnelle.

### 3.3 Step-up : ré-authentification avant un run **live**

Lancer un run **live** (argent réel) exige une **ré-authentification fraîche**, en plus de la garde
existante `confirm_phrase = "I UNDERSTAND"`.

1. Le SPA tente de démarrer un run live. Si aucune autorisation step-up fraîche n'existe, l'API répond
   **403 `step_up_required`**.
2. Le SPA redirige vers `GET /auth/oidc/stepup` → l'API relance une autorisation OIDC avec
   **`max_age=0` + `prompt=login`** (force la ré-authentification).
3. Au retour (`/auth/oidc/stepup/callback`), l'API :
   - valide entièrement le nouvel `id_token` ;
   - vérifie la **fraîcheur de `auth_time`** (≤ 5 min, tolérance d'horloge ≤ 30 s) ;
   - **ré-résout le rôle à partir des `groups` du nouvel id_token** (et pas du rôle figé dans la
     session) — un admin rétrogradé en viewer est ainsi bloqué ;
   - vérifie que le **`sub`** du nouvel id_token correspond à la session courante (pas de step-up croisé
     entre utilisateurs) ;
   - émet une **autorisation à usage unique, à courte durée, liée au `run_id`** concerné.
4. Le SPA relance le démarrage du run, qui passe alors la garde step-up.

> **Note de fiabilité.** Authelia a historiquement eu des défauts de rafraîchissement de `auth_time`
> sur `prompt=login` (authelia#2596). Avant de s'appuyer sur le step-up, on vérifie le comportement de
> la version déployée ; à défaut, on impose une politique `two_factor` au client `trader-api` et/ou on
> conditionne le live à l'âge de session + une nouvelle saisie de `confirm_phrase`.

---

## 4. Validation de l'`id_token` (exigences)

La validation OIDC vit dans un module dédié `api/auth/oidc.py`, **séparé** de `api/auth/jwt.py` (pour
éviter toute confusion entre HS256 — session interne — et RS256 — Authelia).

- **Algorithme** : `RS256` **codé en dur** (`algorithms=["RS256"]`). On refuse `none`, `HS*`, tout algo
  hors JWKS. (Empêche l'attaque de confusion d'algorithme avec la clé publique.)
- **Claims obligatoires** : `iss` (égalité stricte), `aud` (contient le `client_id`), `exp`/`iat`/`nbf`,
  `nonce` (comparaison à temps constant avec le cookie de transaction), `sub` non vide, `auth_time`
  (vérifié au step-up).
- **JWKS** : récupérées via `jwks_uri` (discovery), en **HTTPS**, cache 1 h, un seul rafraîchissement si
  `kid` inconnu (rotation), timeout ≤ 5 s, **fail-closed** (échec ⇒ rejet, jamais d'acceptation par
  défaut).

---

## 5. Sessions, rôles et latence de révocation

- Le **rôle est figé dans le JWT de session au login**. Un changement de groupe dans Authelia n'est donc
  pris en compte qu'à la prochaine connexion (ou expiration de session).
- **TTL de session en prod : 4 h** (au lieu de 24 h) pour borner cette latence.
- Le chemin sensible (run **live**) **ne fait pas confiance au rôle figé** : il ré-résout les groupes via
  le step-up (§3.3). Pour les autres actions admin (config, paper/testnet, activation de poids), la
  latence résiduelle (≤ TTL) est un risque accepté et documenté.

### Cookies

| Cookie               | httpOnly | Secure | SameSite | Domaine                  | Rôle                              |
|----------------------|----------|--------|----------|--------------------------|-----------------------------------|
| `access_token`       | oui      | oui    | Strict   | host-only (`api.trader…`)| Session de l'API (JWT interne)    |
| `csrf_access_token`  | non      | oui    | Strict   | `.trader.derveloy.eu`    | Jeton CSRF double-submit (lisible JS) |
| transaction OIDC     | oui      | oui    | Lax      | host-only                | state/nonce/PKCE **chiffrés**, ≤5 min, usage unique |

`api.trader.derveloy.eu`, `trader.derveloy.eu` et `auth.trader.derveloy.eu` partagent le même domaine
enregistrable `trader.derveloy.eu` → `SameSite=Strict` ne bloque pas les requêtes inter-sous-domaines.

### Protections complémentaires

- **CSRF** : double-submit sur toutes les requêtes mutantes ; comparaison à **temps constant**.
- **Open redirect** : `return_to` validé contre une **liste blanche de chemins relatifs**
  (`^/[A-Za-z0-9/_-]*$`, pas de `//`, pas de `..`) au stockage **et** à l'usage ; sinon `/`.
- **`/no-access`** : aucune fuite d'info (pas de nom de groupe ni de raison) ; aucun cookie émis ;
  cible codée en dur (jamais `return_to`).
- **Limitation de débit** sur les endpoints `/auth/*`.

---

## 6. Développement (auth désactivée)

Authelia exige un domaine → indisponible en local. En dev (`AUTH_MODE=local`) :

- Aucune redirection Authelia ; l'identité et le rôle sont **synthétisés** depuis `DEV_USER_GROUP`
  (ex. `admins` ou `viewers`).
- Le bypass n'est actif **que si** `environment=="dev"` **ET** `auth_mode=="local"` (condition ET,
  jamais OU). En prod, le synthétiseur lève une erreur.
- Le login local par mot de passe (`POST /auth/login`) renvoie **404** dès que `AUTH_MODE != local`
  (suppression du chemin d'auth parallèle).

```bash
# .env (dev)
ENVIRONMENT=dev
AUTH_MODE=local
DEV_USER_GROUP=admins   # ou viewers pour tester la lecture seule
```

---

## 7. Variables d'environnement (prod)

| Variable                     | Description                                                            |
|------------------------------|-----------------------------------------------------------------------|
| `AUTH_MODE`                  | `authelia_oidc` en prod (obligatoire).                                 |
| `AUTHELIA_OIDC_ISSUER`       | URL de l'émetteur Authelia (`https://auth.trader.derveloy.eu`).        |
| `AUTHELIA_OIDC_CLIENT_ID`    | Identifiant du client `trader-api`.                                    |
| `AUTHELIA_OIDC_CLIENT_SECRET`| Secret du client (≥ 32 caractères).                                    |
| `OIDC_TRANSACTION_SECRET`    | Clé de chiffrement du cookie de transaction (≥ 32 caractères, dédiée). |
| `OIDC_ADMIN_GROUP` / `OIDC_VIEWER_GROUP` | Noms des groupes (défauts `admins` / `viewers`).          |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `240` en prod.                                                   |
| `DEV_USER_GROUP`             | Dev uniquement ; ignoré/refusé en prod.                               |

Les secrets propres à Authelia (`AUTHELIA_JWT_SECRET`, `AUTHELIA_SESSION_SECRET`,
`AUTHELIA_STORAGE_ENCRYPTION_KEY`, secret du client OIDC) sont injectés par variables d'environnement /
`secrets:` Docker. **`users_database.yml` (hashes argon2) n'est jamais versionné** et est monté depuis un
chemin VPS absolu (`/etc/authelia/users_database.yml:ro`).

---

## 8. Infrastructure (prod)

- Service `authelia` sur le réseau `trader-network`, routé par Traefik sur `auth.trader.derveloy.eu`
  (entrypoint `websecure` + Let's Encrypt). **Aucun** middleware ForwardAuth sur les routeurs api /
  dashboard.
- `authelia/configuration.yml` (modèle, secrets substitués par variables d'env) déclare :
  - le **fournisseur OIDC** ;
  - le **client `trader-api`** (confidentiel, PKCE S256, redirect URIs vers les callbacks de l'API,
    scopes `openid profile email groups`) ;
  - une **`claims_policy`** plaçant `groups` dans l'`id_token` (requis depuis Authelia v4.39).
- `users_database.yml` (backend fichier) : utilisateurs + groupes `admins` / `viewers`.

---

## 9. Pour aller plus loin

- Plan & suivi : `.agent/authelia-implementation.md`
- Audit de sécurité : `.agent/security-review.md`
- Topologie Traefik : `docs/A4_traefik_topology.md`
- Dev vs prod : `docs/DEV_VS_PROD.md`
