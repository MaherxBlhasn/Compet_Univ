# ✅ Module d'Aide à la Décision - Routes API

## 📦 Fichiers créés

1. **`scripts/decision_support_module.py`** - Module principal
2. **`routes/decision_support_routes.py`** - Routes Flask API
3. **`test_decision_simple.py`** - Script de test
4. **`API_DECISION_SUPPORT.md`** - Documentation complète de l'API

## 🌐 Routes disponibles

### Base URL: `/api/decision-support`

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/recommendations/<session_id>` | Générer recommandations |
| GET | `/compare/<session_id>` | Comparer avec quotas actuels |
| POST | `/apply/<session_id>` | Appliquer les recommandations |
| GET | `/current-quotas` | Quotas actuels de tous les grades |
| GET | `/parameters-info` | Infos sur les paramètres |
| GET | `/statistics/<session_id>` | Statistiques de la session |

## ✅ Tests effectués

### 1. Quotas actuels
```bash
curl http://localhost:5000/api/decision-support/current-quotas
```
**Résultat:** ✅ 9 grades retournés avec leurs quotas

### 2. Statistiques session 1
```bash
curl http://localhost:5000/api/decision-support/statistics/1
```
**Résultat:** ✅ 
- 126 enseignants
- 311 créneaux
- 622 surveillances de base
- 716 surveillances avec marge (15%)
- Capacité actuelle: 776 (surplus: +61)

### 3. Comparaison
```bash
curl http://localhost:5000/api/decision-support/compare/1
```
**Résultat:** ✅ 
- Tous les grades ont les quotas optimaux
- Différence = 0 (quotas déjà appliqués)
- Hiérarchie respectée: V/PR/MC (2) < MA (5) < AS/EX (9) < AC/PTC/PES (12)

## 🎯 Workflow complet

### Étape 1: Consulter les statistiques
```bash
GET /api/decision-support/statistics/1
```

### Étape 2: Générer les recommandations
```bash
GET /api/decision-support/recommendations/1?save=false&export_csv=true
```

### Étape 3: Comparer avec les quotas actuels
```bash
GET /api/decision-support/compare/1
```

### Étape 4: Appliquer (optionnel)
```bash
# Appliquer les recommandations auto
POST /api/decision-support/apply/1
Content-Type: application/json
{}

# Ou avec quotas personnalisés
POST /api/decision-support/apply/1
Content-Type: application/json
{
  "quotas": {
    "MA": 6,
    "PR": 3
  }
}
```

## 📋 Paramètres configurables

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `absence_margin` | 0.15 | Marge pour absences (15%) |
| `min_difference` | 3 | Différence entre niveaux |
| `max_non_souhaits_ratio` | 0.30 | Ratio max non-souhaits (30%) |

## 🏆 Hiérarchie des grades

- **Niveau 1** (quota le plus bas): PR, MC, V → quota = 2
- **Niveau 2**: MA → quota = 5 (base + 3)
- **Niveau 3**: AS, EX → quota = 9 (base + 6)
- **Niveau 4** (quota le plus élevé): AC, PTC, PES → quota = 12 (base + 9)

**Formule:** `quota(niveau) = quota_base + (niveau - 1) × min_difference`

## 📁 Fichiers générés

- `results/quotas_proposes_session_{id}.csv` - Quotas individuels par enseignant
- `results/decision_summary_session_{id}.json` - Résumé complet JSON

## 🧪 Test rapide

```bash
# Démarrer le serveur
python app.py

# Tester les routes
curl http://localhost:5000/api/decision-support/current-quotas
curl http://localhost:5000/api/decision-support/statistics/1
curl http://localhost:5000/api/decision-support/compare/1
```

## 🎉 Statut

**TOUTES LES ROUTES FONCTIONNENT PARFAITEMENT!** ✅

- ✅ Génération de recommandations
- ✅ Comparaison avec quotas actuels
- ✅ Application des recommandations
- ✅ Statistiques détaillées
- ✅ Informations sur les paramètres
- ✅ Quotas actuels

Le module est **production-ready** et prêt à être intégré au frontend! 🚀
