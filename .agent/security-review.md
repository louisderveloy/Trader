# Security Review — Trader Bot

> Audit réalisé le **2026-06-12** par l'agent `security-reviewer` sur l'ensemble de la stack
> (API FastAPI, bot Python, dashboard Vue 3, PostgreSQL/TimescaleDB, Docker/Traefik, dépendances).
>
> Ce fichier est **vivant** : cocher les cases au fur et à mesure des corrections.

## Bilan global : risque **ÉLEVÉ**

| Sévérité    | Nombre |
|-------------|--------|
| 🔴 Critique | 2      |
| 🟠 Élevé    | 6      |
| 🟡 Moyen    | 7      |
| 🔵 Faible   | 5      |
| ⚪ Info      | 3      |
| **Total**   | **23** |

La base est solide : JWT en cookie `httpOnly`, CSRF double-submit, requêtes SQL 100 % paramétrées
(aucune injection), superviseur de commandes en `create_subprocess_exec` (pas de shell) avec allowlist
argv, rôle Grafana read-only. Les problèmes critiques/élevés sont concentrés sur la DB exposée et la
librairie JWT abandonnée.

---

## TODO — Suivi des corrections

### 🔐 Authelia OIDC — revue de conception (2026-06-14)

> Findings issus de la revue `security-reviewer` du design Authelia OIDC (BFF + Authorization
> Code/PKCE). Statut au fil de l'implémentation (branche `feature/authelia-implementation`).
> Détail complet : `.agent/authelia-implementation.md` + `docs/Authentification.md`.

- [x] **AO-1** Step-up live : ré-résolution du rôle depuis l'id_token frais + binding du `sub` à la
  session + grant usage-unique — `api/auth/oidc_routes.py` (`oidc_stepup_callback`), `api/routes/runs.py`
  (`_require_stepup_for_live`). _Note : grant Fernet httpOnly stateless ; usage-unique via clear-cookie
  + lock instance live. Migration DB pour usage-unique strict multi-worker = follow-up._
- [x] **AO-2** Boot refusé si `prod` & `auth_mode != authelia_oidc` ; CORS wildcard refusé en prod —
  `api/config.py:validate_production_secrets`.
- [x] **AO-3** `/auth/login` → 404 hors mode local — `api/auth/routes.py:_require_local_mode`.
- [x] **AO-4** Validation id_token RS256-only, claims complètes, JWKS fail-closed, module séparé de
  `jwt.py` — `api/auth/oidc.py:validate_id_token`.
- [x] **AO-5** Cookie de transaction chiffré (Fernet), usage unique, ≤5 min, secret dédié —
  `api/auth/oidc.py` + `api/auth/cookies.py:set_txn_cookie`.
- [x] **AO-6** `return_to` : allowlist chemin relatif (stockage + usage) — `api/auth/oidc_routes.py:_safe_return_to`.
- [x] **AO-7** Domaines cookies resserrés (session host-only, CSRF `.trader.derveloy.eu`) +
  `SameSite=Strict` — `api/auth/cookies.py`. **Remplace l'avis de #6** (domaine plus étroit que
  `.derveloy.eu`).
- [x] **AO-8/15** Secrets OIDC validés en prod ; `users_database.yml` gitignoré + monté hors-repo —
  `api/config.py`, `.gitignore`, `authelia/` (template uniquement).
- [x] **AO-12** Comparaison CSRF à temps constant — `api/csrf_helper.py`.
- [ ] **AO-11** TTL session prod → 240 min : documenté (`.env.example`) mais **non forcé** par
  validation. _Couvre partiellement #12._
- [ ] **AO-RISK** Vérifier que `prompt=login`/`max_age=0` rafraîchit bien `auth_time` sur la version
  Authelia déployée (authelia#2596) ; sinon fallback `two_factor`.
- [ ] **AO-FOLLOWUP** Migrer `api/auth/oidc.py` de `authlib.jose` (déprécié) vers `joserfc` avant
  Authlib 2.0 (pin actuel `<2.0`).

### 🔴 Critiques (semaine 1)

- [x] **#1** Remplacer `python-jose` par `PyJWT>=2.8.0` ; coder en dur `algorithms=["HS256"]` et `options={"require":["exp","sub"]}` — `api/requirements.txt:14`, `api/auth/jwt.py:73-95`. _Fait : PyJWT swap, HS256 littéral encode+decode, require exp/sub ; `jwt_algorithm` config marqué unused ; régression `api/tests/test_jwt.py` (alg=none/no-sub/no-exp/wrong-secret rejetés). 37 tests API passent._
- [ ] **#2** Binder PostgreSQL sur `127.0.0.1:5432:5432` (tunnel SSH/VPN pour Grafana externe) + mot de passe Grafana readonly non vide validé — `docker-compose.prod.yml:41`

### 🟠 Élevés (semaine 1-2)

- [x] **#3** Allowlist regex sur `study_name` (API + superviseur) — `api/models/run_control.py`, `bot/runs/supervisor.py`. _Fait : regex corrigée `^[A-Za-z0-9_][A-Za-z0-9_\- ]{0,99}$` (1er char non-tiret — la regex initiale de la review autorisait `--n-trials` ⇒ ne rejetait rien) ; byte-identique dans les 2 fichiers ; tests `test_run_supervisor_validation` + `api/tests/test_run_control_validation`. Menace réelle = crash du run (argv token unique, pas d'injection shell), durcissement défense-en-profondeur._
- [ ] **#4** Valider en prod l'absence de mot de passe admin faible (`admin/admin`) + exiger `ADMIN_PASSWORD_HASH` ; durcir le rate limit login (5→3/min) — `api/config.py:75,297`
- [ ] **#5** Valider `CSRF_SECRET_KEY` en prod (≥32 chars, pas de pattern "generate") — `api/config.py:85-89,265-299`
- [x] **#6** Cookie `SameSite=Strict` en prod — **déjà résolu par AO-7** (refactor cookies). Le policy cookie vit dans `api/auth/cookies.py:33` (`_samesite() = "strict" if prod else "lax"`), pas dans `routes.py` (refs obsolètes). Prod = Strict confirmé : `docker-compose.prod.yml:170,198` posent `ENVIRONMENT: prod` (match exact `config.py:324`). Domaine plus étroit qu'`.derveloy.eu` (session host-only, CSRF `.trader.derveloy.eu`). Lax conservé en dev (non exposé, cookies non-Secure) et sur le cookie txn OIDC (nécessaire pour la nav top-level depuis Authelia). Aucun changement de code.
- [x] **#7** User non-root dans les images prod — `bot/Dockerfile`, `api/Dockerfile`, `dashboard/Dockerfile.prod`. _Fait & vérifié au runtime via `docker run` (mount G: HS) :_
  - _**api** → `USER app` (uid 999) ; lit `bot_logs` en RO, bind 8000 non-privilégié. 47 tests API OK._
  - _**bot** → drop root→app auto-réparant via `gosu` dans `entrypoint.sh` (PID1 root chown le volume `bot_logs` qui peut préexister root-owned, puis re-exec en `app`). Évite tout chown manuel au déploiement (pas de downtime du bot live). `PYTHONDONTWRITEBYTECODE=1` (alembic importe `/db/migrations` depuis un mount host). **Hypothèse déploiement : `./db` doit être world-readable pour que `app` lance alembic.**_
  - _**dashboard** → base `nginxinc/nginx-unprivileged:alpine` (uid 101 `nginx`), `listen 8080`, HEALTHCHECK + label Traefik `loadbalancer.server.port` → 8080. `/health` → 200 vérifié._
  - _Dashboard **dev** (`dashboard/Dockerfile`, vite) laissé en root : local uniquement, hors scope._
- [ ] **#8** Insérer un `docker-socket-proxy` entre Traefik et le daemon Docker — `docker-compose.prod.yml:74`

### 🟡 Moyens (mois 1)

- [x] **#9** Pinner les images Docker — `docker-compose.yml:27`, `docker-compose.prod.yml:27`. _Fait : `timescale/timescaledb` pinné **par digest** `@sha256:51ac20ec…` (= image en service, TimescaleDB 2.27.2 / PG 16.14). Découverte : `latest-pg16` ≠ `2.27.2-pg16` dans le registry (le tag flottant a déjà bougé depuis le pull d'il y a 2 sem.) ⇒ pin sur le digest des bytes réellement déployés/testés, pas sur un tag de version. Validé : compose parse, digest résolvable. `traefik:v3.7` / `authelia:4.39` laissés en pin mineur (acceptable) ; images `ghcr.io/.../trader-*:latest` gérées par la CD (`pull_policy: always`), hors scope._
- [x] **#10** Retirer `--reload` du CMD du Dockerfile API (opt-in via env) — `api/Dockerfile`. _Fait : CMD → `python -m api.main` (launcher existant, dont l'import string cassé `main:app` est corrigé en `api.main:app`) ; `api_reload` défaut `True`→`False` ; dev compose pose `API_RELOAD=true`. Vérifié : sans env = "Started server process" (pas de reloader) ; `API_RELOAD=true` = "Started reloader process … WatchFiles". 47 tests API OK. **Worker unique conservé volontairement** : le store rate-limit slowapi est en mémoire (pas de Redis) ⇒ multi-worker fractionnerait les buckets et affaiblirait l'anti-brute-force. `API_WORKERS=4` reste donc dead config (suivi : nécessite un backend partagé avant d'augmenter les workers)._
- [x] **#11** Allowlist `symbol` (`AVAILABLE_SYMBOLS`) sur `/config/user-indicator` — `api/routes/config.py`. _Fait : dépendance `valid_symbol` (strip/upper + membership → 422) sur GET & PATCH ; défaut `BTCUSDT`→`settings.binance_default_symbol` (BTCUSDC). **Bug latent corrigé** : le front écrivait `user_indicator` sous `BTCUSDT` alors que le bot lit `BTCUSDC` ⇒ l'indicateur utilisateur n'atteignait jamais le bot. Front aligné sur BTCUSDC (`api/config.ts`, `stores/config.ts`, `UserIndicatorView.vue`). Tests `api/tests/test_config_symbol_validation.py` (dont l'invariant no-arg=défaut). 53 tests API OK ; dashboard build (vue-tsc) OK._
- [~] **#12** Réduire la durée de vie JWT — `api/config.py`, `.env.example`. _Partiel (choix user : réduction TTL seule) : `jwt_access_token_expire_minutes` 1440→**120 min** (default + .env.example). Supersede AO-11 (240 prod) par une valeur plus stricte appliquée à tous les envs. **Refresh/révocation (token version en DB) = follow-up non fait** — pas de révocation serveur, le logout n'invalide pas le token avant expiration. 53 tests API OK._
- [x] **#13** Webhook Discord redacté dans les logs — `bot/notifications/discord.py`. _Fait (choix user : **garder `response.text`**, masquer le token) : vrai vecteur = les exceptions httpx embarquent l'URL (avec token) dans `str(e)`. `error_message` passe par `redact()` (`utils/log_redaction.py`, déjà existant, masque les URLs webhook Discord) dans les 2 branches ; `logger.error` loggue le message redacté. `response.text` conservé. Tests `tests/test_discord_redaction.py` : token absent + `response.text` présent. 2/2 OK._
- [x] **#14** README corrigé + garde `lastRoute` — `dashboard/src/router/index.ts`, `dashboard/README.md`. _Fait : `lastRoute` accepté seulement si chemin relatif same-origin (`startsWith('/')` ET pas `//host` protocol-relative ET ≠ `/login`) ; README ligne 30 corrigé (JWT en cookie httpOnly, plus localStorage). vue-tsc build OK._
- [x] **#15** Rate limiter sur vraie IP client — `api/limiter.py`, `api/auth/routes.py`. _Fait : `client_ip_key_func` prend l'entrée **la plus à droite** de X-Forwarded-For (= peer réel ajouté par Traefik), fallback socket peer si pas de XFF/malformé. **Vérifié via Context7** (Traefik v3.7 `notAppendXForwardedFor=false` par défaut ⇒ append le vrai peer ; pas d'`insecure`, `trustedIPs` vide ⇒ XFF client non fiable) → rightmost non spoofable avec 1 hop. Pas de changement Traefik nécessaire (défaut sûr). Logs login (échec+succès) utilisent aussi la vraie IP. Tests `api/tests/test_limiter_key.py` (dont assertion anti-spoof `1.1.1.1, 5.6.7.8`→`5.6.7.8`). 57 tests API OK. **Dépend du worker unique de #10** : un futur multi-worker exige un store rate-limit partagé ET de recompter les hops si un CDN s'ajoute._
- [ ] **#16** Remplacer `'unsafe-inline'` (style-src) par CSP hash/nonce — `dashboard/nginx.conf:21,62`

### 🔵 Faibles

- [x] **#17** Distinguer token expiré vs forgé dans les logs — `api/auth/jwt.py`. _Fait : `decode_access_token` catch `jwt.ExpiredSignatureError` → `logger.debug` (bénin) vs autre `jwt.PyJWTError` → `logger.warning` (forge/tampering possible, nom de l'exception loggé). Tests log-level dans `api/tests/test_jwt.py` (expiré=debug sans warning ; wrong-secret=warning). 7 tests jwt OK._
- [ ] **#18** Documenter le risque du bind-mount source RW en dev (OK en prod) — `docker-compose.yml:67`
- [x] **#19** Default DB password vide + validation non-vide tous envs — `api/config.py`. _Fait : `postgres_password` default `"password"`→`""` ; check non-vide en tête de `validate_production_secrets` (avant le bloc prod, tous envs). Champ load-bearing (vérifié : `api/database.py:51` passe `settings.postgres_password` à `asyncpg.create_pool`). CI `api-test` + runs de test posent `POSTGRES_PASSWORD` (le `Settings()` module-level tourne à l'import). Vérifié : import sans le var → fail-fast clair ; tests `Settings(postgres_password="")`→ValueError. 61 tests API OK._
- [ ] **#20** Valider la présence des clés Binance au démarrage (avant lock instance) — `bot/scripts/trading.py`, `bot/exchanges/binance.py`
- [ ] **#21** (Info) Pinner les dépendances (`pip freeze` → `requirements-pinned.txt`) — `api/requirements.txt`, `bot/requirements.txt`

### ⚪ Info / hygiène

- [ ] **#22** HSTS conditionné sur `$scheme = https` dans nginx — `dashboard/nginx.conf:31,52,65`
- [ ] **#23** Déplacer `optuna-dashboard` en dépendance dev (ou retirer) — `bot/requirements.txt:26`
- [ ] **CI** Ajouter `pip-audit` (bot) + `npm audit` (dashboard), échec du pipeline sur HIGH/CRITICAL

---

## Détail des findings

### 🔴 FINDING 1 — CRITIQUE — Dépendance JWT vulnérable (CVE-2022-29217)

- **Localisation** : `api/requirements.txt:14` ; `api/auth/jwt.py:73-76,91-93`
- **Description** : l'API utilise `python-jose[cryptography]>=3.3.0`, affecté par CVE-2022-29217
  (algorithm confusion : substitution d'un algo faible `none`/`RS256` via le header `alg`). Librairie
  non maintenue depuis 2023. Le passage d'`algorithms=[...]` en liste aide mais ne ferme pas
  complètement la faille.
- **Risque** : token forgé → accès admin à tous les endpoints, y compris lancement de runs **live
  mainnet** (argent réel).
- **Fix** :
  1. Remplacer `python-jose[cryptography]` par `PyJWT>=2.8.0`.
  2. Réécrire `api/auth/jwt.py` :
     ```python
     import jwt  # PyJWT
     encoded = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
     decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"],
                          options={"require": ["exp", "sub"]})
     ```
  3. `algorithms=` doit être un littéral codé en dur (`["HS256"]`), jamais lu depuis le token.
- **Vérif** : envoyer un token `alg=none` → 401.

### 🔴 FINDING 2 — CRITIQUE — DB exposée sur toutes les interfaces en prod

- **Localisation** : `docker-compose.prod.yml:41` (binding `"0.0.0.0:5432:5432"`) ; commentaire 163-177
- **Description** : PostgreSQL exposé sur internet ; la seule protection (`ufw`) est dans des
  commentaires, non appliquée. `POSTGRES_GRAFANA_READONLY_PASSWORD` vide par défaut (`.env.example:48`).
  Si l'opérateur suit le commentaire "legacy" et utilise `${POSTGRES_USER}` pour Grafana, le credential
  read-write complet est exposé.
- **Risque** : brute-force/credential-stuffing direct sur PostgreSQL → accès complet aux trades, à
  `run_commands` (start/stop/kill), à `weights_sets`.
- **Fix** :
  1. Binder sur `"127.0.0.1:5432:5432"` ; accès Grafana externe via tunnel SSH (`ssh -L 5432:localhost:5432`).
  2. Alternative : `pg_hba.conf` n'autorisant que l'IP Grafana pour le rôle `grafana_readonly`.
  3. Définir un `POSTGRES_GRAFANA_READONLY_PASSWORD` fort, validé dans `api/config.py`.
  4. Déplacer l'exigence firewall d'un commentaire vers une checklist de déploiement versionnée.
- **Vérif** : `nmap -p 5432 <vps-ip>` depuis l'extérieur → `filtered`.

### 🟠 FINDING 3 — ÉLEVÉ — Argument injection via `study_name` non filtré

- **Localisation** : `bot/runs/supervisor.py:151-154,220` ; `api/models/run_control.py:236,283`
- **Description** : `study_name` validé seulement non-vide + `max_length=100`, puis passé en argv via
  `["--study-name", params["study_name"]]`. `create_subprocess_exec` (pas de shell) empêche l'injection
  de code, mais une valeur commençant par `--` pourrait être réinterprétée comme flag par l'argparse
  enfant. Gap de défense (pas d'allowlist de caractères).
- **Risque** : un admin pourrait injecter un flag (`--n-trials 99999`) ou faire échouer le run.
- **Fix** : `field_validator` regex `r"[A-Za-z0-9_\- ]{1,100}"` côté API + re-check dans le superviseur.
- **Vérif** : `"study_name": "--n-trials 99999"` → 422.

### 🟠 FINDING 4 — ÉLEVÉ — Mot de passe admin faible non validé en prod

- **Localisation** : `api/config.py:75,297` ; `.env.example:104-108`
- **Description** : défaut `ADMIN_PASSWORD=admin` / `ADMIN_USERNAME=admin`. `validate_production_secrets`
  saute la validation admin ("Authelia replacera l'auth") mais Authelia est stubbé (501). Le mode local
  est le seul opérationnel. Rate limit login 5/min trop permissif contre un mdp 4 caractères.
- **Risque** : brute-force de `/auth/login`.
- **Fix** : exiger `ADMIN_PASSWORD_HASH` en prod, rejeter usernames communs, durcir le rate limit (3/min),
  ajouter un lockout progressif.
- **Vérif** : déployer avec `ADMIN_PASSWORD=admin` en prod → échec startup.

### 🟠 FINDING 5 — ÉLEVÉ — Cookie `SameSite=Lax` au lieu de `Strict`

- **Localisation** : `api/auth/routes.py:77,151`
- **Description** : cookies `access_token`/`csrf_access_token` en `samesite="lax"`. La justification
  cross-sous-domaine est erronée : `api.derveloy.eu` et `bot.derveloy.eu` partagent `derveloy.eu`
  (same-site), `Strict` ne les bloque pas. Le CSRF token compense, mais défense en profondeur souhaitable.
- **Risque** : marginal (POST top-level navigation depuis site externe), couvert par le CSRF token.
- **Fix** : `samesite="strict"` + `domain=".derveloy.eu"` en prod ; tester les appels cross-sous-domaine.
- **Vérif** : Set-Cookie montre `SameSite=Strict`.

### 🟠 FINDING 6 — ÉLEVÉ — `CSRF_SECRET_KEY` jamais validé en prod

- **Localisation** : `api/config.py:85-89,265-299`
- **Description** : défaut `"generate_csrf_secret_with_openssl_rand_hex_32"`. `validate_production_secrets`
  valide JWT et POSTGRES mais pas CSRF → valeur prédictible possible en prod.
- **Risque** : forge de tokens CSRF → toute opération state-changing.
- **Fix** : rejeter en prod si `"generate" in csrf_secret_key.lower()` ou `len < 32`.
- **Vérif** : valeur par défaut en prod → échec startup.

### 🟠 FINDING 7 — ÉLEVÉ — Tous les conteneurs tournent en root

- **Localisation** : `bot/Dockerfile`, `api/Dockerfile`, `dashboard/Dockerfile` (aucun `USER`)
- **Description** : tous les process en UID 0. Compromission applicative → root conteneur → lecture du
  `.env` monté / variables d'env.
- **Risque** : escalade de privilèges, potentiel breakout.
- **Fix** :
  ```dockerfile
  RUN addgroup --system app && adduser --system --ingroup app app
  USER app
  ```
  Rendre `entrypoint.sh` et `/var/log/trader-bot` accessibles au user non-root.
- **Vérif** : `docker compose exec bot id` → `uid=NNN(app)`.

### 🟠 FINDING 8 — ÉLEVÉ — Socket Docker monté dans Traefik

- **Localisation** : `docker-compose.prod.yml:74`
- **Description** : `/var/run/docker.sock:ro` donne accès en lecture à toutes les variables d'env des
  conteneurs (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `BINANCE_MAINNET_API_KEY`, `DISCORD_WEBHOOK_URL`…).
- **Risque** : compromission Traefik → vol de tous les secrets → trades non autorisés.
- **Fix** : `tecnativa/docker-socket-proxy` exposant uniquement `containers`/`networks`/`services` en
  lecture ; ou file provider Traefik sans socket.
- **Vérif** : Traefik ne peut plus `docker inspect`.

### 🟡 FINDING 9 — MOYEN — Tags d'images Docker non pinnés

- **Localisation** : `docker-compose.yml:27`, `docker-compose.prod.yml:27`
- **Description** : `timescale/timescaledb:latest-pg16` (tag flottant) → changements non revus,
  substitution de chaîne d'approvisionnement.
- **Fix** : pinner (`timescale/timescaledb:2.17.2-pg16`, `node:20-alpine` patch précis).
- **Vérif** : `docker image inspect` montre un SHA fixe.

### 🟡 FINDING 10 — MOYEN — `--reload` par défaut dans le Dockerfile API

- **Localisation** : `api/Dockerfile:22`
- **Description** : CMD avec `--reload`. La prod l'override (`API_RELOAD: false`) mais un `docker run`
  direct démarre avec auto-reload (exposition de code via file-watch, CPU).
- **Fix** : retirer `--reload` du CMD, opt-in via env.
- **Vérif** : `docker run <api-image>` sans compose → pas de watcher.

### 🟡 FINDING 11 — MOYEN — `symbol` non allowlisté sur `/config/user-indicator`

- **Localisation** : `api/routes/config.py:271,323`
- **Description** : `symbol` free-form (défaut `BTCUSDT`), passé en requête paramétrée (pas d'injection
  SQL) mais permet de polluer `user_indicator` avec des symboles fictifs.
- **Fix** : `field_validator` contre `AVAILABLE_SYMBOLS`.
- **Vérif** : `symbol='; DROP TABLE...` → 422.

### 🟡 FINDING 12 — MOYEN — JWT 24h sans refresh/révocation

- **Localisation** : `.env.example:91`, `api/config.py:60`, `api/auth/jwt.py:63-76`
- **Description** : `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440`. Pas de refresh ni révocation côté serveur ;
  cookie volé valide 24h, pas d'invalidation au logout.
- **Fix** : réduire à 60 min ; access court (15min) + refresh ; ou token version en DB incrémentée au logout.
- **Vérif** : logout puis requête avec ancien JWT → 401.

### 🟡 FINDING 13 — MOYEN — Webhook Discord potentiellement loggé

- **Localisation** : `bot/notifications/discord.py:122-130`
- **Description** : `DISCORD_WEBHOOK_URL` contient le token webhook. Les erreurs loggent
  `response.text` ; le `webhook_url` stocké sur l'objet pourrait fuiter via un repr/exception.
- **Fix** : ne logger que l'ID webhook (`url.split("/")[-2]`), ne pas logger `response.text`.
- **Vérif** : provoquer une erreur Discord → aucun token dans les logs.

### 🟡 FINDING 14 — MOYEN — `lastRoute` localStorage + doc README erronée

- **Localisation** : `dashboard/src/router/index.ts:91,110` ; `dashboard/README.md:30`
- **Description** : `lastRoute` lu et passé à `next()` sans sanitization (risque faible car `fullPath`
  toujours relatif). Le README documente à tort "JWT token (localStorage)" alors qu'il est en cookie
  httpOnly → risque d'induire un futur contributeur en erreur.
- **Fix** : corriger le README ; garde `lastRoute.startsWith('/') && lastRoute !== '/login'`.
- **Vérif** : `localStorage.lastRoute = 'javascript:alert(1)'` → pas d'exécution au redirect.

### 🟡 FINDING 15 — MOYEN — Rate limiting cassé derrière Traefik

- **Localisation** : `api/limiter.py:15-18`, `api/auth/routes.py:26`
- **Description** : `get_remote_address` voit l'IP interne Docker de Traefik → bucket partagé par tous.
  Si `X-Forwarded-For` est pris naïvement, il est spoofable.
- **Fix** : `key_func` lisant le `X-Forwarded-For` gauche, Traefik `trustedIPs` configuré.
- **Vérif** : 6 logins depuis le même client via Traefik → 6e en 429.

### 🟡 FINDING 16 — MOYEN — CSP `'unsafe-inline'` sur style-src

- **Localisation** : `dashboard/nginx.conf:21,62`
- **Description** : `style-src 'self' 'unsafe-inline'` (Tailwind). Permet l'injection CSS
  (exfiltration via `url()`, sélecteurs d'attributs lisant des valeurs de formulaire).
- **Fix** : CSP hash/nonce (`vite-plugin-csp`) ou classes Tailwind uniquement.
- **Vérif** : retirer `'unsafe-inline'`, dashboard rend sans violation CSP.

### 🔵 FINDING 17 — FAIBLE — Pas de distinction token expiré vs forgé

- **Localisation** : `api/auth/jwt.py:91-95`
- **Description** : `JWTError` capturé génériquement → impossible de détecter les tentatives de forge
  dans les logs.
- **Fix** : logger distinctement `ExpiredSignatureError` (debug) vs autre `JWTError` (warning forge).

### 🔵 FINDING 18 — FAIBLE — Bind-mount source RW en dev

- **Localisation** : `docker-compose.yml:67`
- **Description** : `./bot:/app` en RW (hot-reload). Compromission conteneur → modification des sources
  hôte. Standard en dev, absent en prod (correct).
- **Fix** : documenter le risque ; confirmer l'absence en prod (déjà le cas).

### 🔵 FINDING 19 — FAIBLE — Default DB password dans le code

- **Localisation** : `api/config.py:40`
- **Description** : `postgres_password: str = Field(default="password")`. Jamais utilisé en pratique
  (override compose + validation prod) mais donne un faux sentiment qu'un env manquant est acceptable.
- **Fix** : défaut `""` + validation non-vide tous environnements.

### 🔵 FINDING 20 — FAIBLE — Clés Binance non validées au démarrage

- **Localisation** : `bot/scripts/trading.py`, `bot/exchanges/binance.py`
- **Description** : pas de check non-vide de la clé sélectionnée (testnet/mainnet) avant connexion →
  `None` passé au SDK, erreur obscure.
- **Fix** : valider la présence clé/secret avant d'acquérir le lock instance.

### ⚪ FINDING 21 — INFO — Dépendances en `>=` au lieu de pins exacts

- **Localisation** : `api/requirements.txt`, `bot/requirements.txt`
- **Fix** : `requirements-pinned.txt` via `pip freeze` pour les builds prod.

### ⚪ FINDING 22 — INFO — HSTS envoyé même en HTTP

- **Localisation** : `dashboard/nginx.conf:31,52,65`
- **Description** : HSTS sur le listener port 80 (ignoré par les navigateurs en HTTP, mais erreur de
  config).
- **Fix** : conditionner sur `if ($scheme = https)`.

### ⚪ FINDING 23 — INFO — `optuna-dashboard` en dépendance non-dev

- **Localisation** : `bot/requirements.txt:26`
- **Description** : installe un serveur web complet dans le conteneur bot (surface d'attaque, taille).
- **Fix** : déplacer en `requirements-dev.txt` ou retirer.

---

## Contrôles validés (déjà bien implémentés)

- JWT en cookie `httpOnly` (pas lisible par JS) — `api/auth/routes.py`
- CSRF double-submit cookie sur tous les endpoints state-changing — `api/csrf_helper.py`
- Requêtes SQL 100 % paramétrées (asyncpg `$1,$2…`), aucune injection trouvée
- Superviseur `run_commands` : `create_subprocess_exec` (pas de shell) + allowlist argv + re-validation
- Rôle Grafana read-only via migration 012 (SELECT only)
- `StartRunRequest` Pydantic `extra='forbid'` (anti mass-assignment)
- `secrets.compare_digest` pour la comparaison de credentials (anti timing-attack)
- Délai aléatoire (0.1–0.3 s) au login (anti brute-force)
- Handler d'erreur prod : message générique sans stack trace
- En-têtes de sécurité HTTP (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
  Permissions-Policy) appliqués via middleware
- Domaine cookie scopé `.derveloy.eu` en prod (pas wildcard)
- Kill commands restreints aux runs backtest/optim (paper/live protégés)
- Run live mainnet exige `confirm_phrase == "I UNDERSTAND"` (`secrets.compare_digest`)
- `ADMIN_PASSWORD_HASH` prioritaire (bcrypt), fallback plaintext dev only
- API Dockerfile ne monte pas le socket Docker
- `.env` dans `.gitignore`, aucun credential réel dans l'historique git
