# Trading Bot Dashboard - Vue 3 Frontend

Dashboard Vue.js pour le bot de trading crypto (Phase 9 - Wave 1 MVP).

## Stack Technique

- **Vue 3** (Composition API) - Framework frontend
- **TypeScript** - Typage statique
- **Vite** - Build tool
- **Pinia** - State management
- **Vue Router** - Routing avec guards d'authentification
- **TailwindCSS** - Styling (thème clair uniquement)
- **Axios** - Client HTTP avec intercepteurs JWT
- **date-fns** - Formatage de dates

## Wave 1 (MVP) - Fonctionnalités Implémentées

### Pages
- ✅ **Login** - Authentification JWT
- ✅ **Home** - État du bot, P&L (placeholder), liens Grafana optionnels
- ✅ **Runs** - Liste des runs avec filtres et pagination

### Composants
- ✅ Layout (AppHeader, AppSidebar, AppLayout)
- ✅ Common (LoadingSpinner, ErrorAlert, EmptyState)
- ✅ Home (BotStatus avec polling 10s, PnLSummary)
- ✅ Runs (RunCard, RunStatusBadge)

### Stores (Pinia)
- ✅ Auth - JWT session en cookie httpOnly (jamais lisible par JS), login/logout
- ✅ Runs - Liste des runs, polling actifs
- ✅ UI - État sidebar (mobile)

### Features
- ✅ JWT authentication avec auto-logout sur 401
- ✅ Polling actif runs (10 secondes)
- ✅ Filtres runs (type, status, symbol)
- ✅ Pagination
- ✅ Responsive design (mobile, tablet, desktop)

## Setup

### 1. Installer les dépendances

```bash
cd G:\dev\Trader\dashboard
npm install
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Éditer `.env` :
```
VITE_API_BASE_URL=http://localhost:8000
VITE_GRAFANA_BASE_URL=  # Optionnel
```

### 3. Lancer en développement

```bash
npm run dev
```

Dashboard accessible sur http://localhost:5173

### 4. Build pour production

```bash
npm run build
```

Les fichiers seront générés dans `dist/`.

## Docker

### Dev local

```bash
docker-compose up dashboard
```

### Production

```bash
docker-compose -f docker-compose.prod.yml up dashboard
```

## Structure du Projet

```
dashboard/
├── src/
│   ├── api/              # API client + endpoints
│   │   ├── client.ts     # Axios avec JWT interceptors
│   │   ├── types.ts      # Types API
│   │   ├── auth.ts       # Auth endpoints
│   │   └── runs.ts       # Runs endpoints
│   ├── components/
│   │   ├── common/       # Composants réutilisables
│   │   ├── layout/       # Layout (Header, Sidebar)
│   │   ├── home/         # Composants Home
│   │   └── runs/         # Composants Runs
│   ├── stores/           # Pinia stores
│   │   ├── auth.ts       # Authentification
│   │   ├── runs.ts       # Runs + polling
│   │   └── ui.ts         # UI state
│   ├── router/           # Vue Router
│   ├── views/            # Pages
│   │   ├── LoginView.vue
│   │   ├── HomeView.vue
│   │   ├── RunsView.vue
│   │   └── PlaceholderView.vue (Wave 2-3)
│   ├── utils/            # Utilitaires
│   │   ├── format.ts     # Formatage dates/nombres
│   │   └── constants.ts  # Constantes app
│   ├── types/            # Types TypeScript
│   ├── App.vue           # Composant root
│   ├── main.ts           # Entry point
│   └── style.css         # Tailwind CSS
├── public/
├── index.html
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── package.json
└── Dockerfile
```

## Authentification

- **Login**: `POST /auth/login` avec username/password
- **Token JWT**: Stocké dans localStorage
- **Auto-logout**: Sur réponse 401 de l'API
- **Guards**: Routes protégées redirigent vers `/login`

Credentials par défaut (configurables dans `G:\dev\Trader\.env`):
- Username: `admin`
- Password: `admin`

## Polling

- **Active runs**: Polling toutes les 10 secondes sur Home page
- **Stop automatique**: Polling s'arrête quand le composant unmount

## API Endpoints Utilisés (Wave 1)

- ✅ `POST /auth/login` - Login
- ✅ `GET /auth/me` - User info
- ✅ `GET /runs` - Liste runs
- ✅ `GET /runs/active` - Runs actifs
- ✅ `GET /runs/{id}` - Détail run
- ✅ `PATCH /runs/{id}/status` - Update status

## Pages Futures (Wave 2-3)

Les routes suivantes affichent un placeholder "Prochainement" :
- ⏳ `/configuration` - Configuration paramètres (Wave 2, endpoint `/config` requis)
- ⏳ `/user-indicator` - Indicateur utilisateur (Wave 2, endpoint `/indicators/user` requis)
- ⏳ `/optimizations` - Études Optuna (Wave 3, endpoint `/optimizations` requis)
- ⏳ `/trades` - Historique trades (Wave 3, endpoint `/trades` requis)
- ⏳ `/logs` - Logs et erreurs (Wave 3, endpoint `/logs` requis)

## Scripts npm

- `npm run dev` - Dev server (port 5173)
- `npm run build` - Build production
- `npm run preview` - Preview build
- `npm run lint` - Lint code
- `npm run format` - Format code (Prettier)

## Notes de Développement

### Thème
- **Light theme uniquement** (per CLAUDE.md)
- Palette de couleurs : Primary (bleu), Success (vert), Warning (jaune), Danger (rouge)

### Conventions
- **Vue 3 Composition API uniquement** (pas d'Options API)
- **TypeScript strict** sur toutes les fonctions
- **Responsive first** - Mobile, tablet, desktop

### Grafana
- Liens optionnels vers Grafana externe (hébergé séparément)
- Pas de graphes complexes développés en Vue.js (per CLAUDE.md)
- Vue.js = configuration + actions uniquement

## Testing (Phase 12)

Tests prévus pour Phase 12 :
- Unit tests (stores, utils)
- Component tests (views, components)
- E2E tests (user flows)

## Support

Pour toute question, voir la documentation principale dans `G:\dev\Trader\CLAUDE.md`.
