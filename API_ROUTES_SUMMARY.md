# 📚 Résumé des Routes API - Système de Surveillance

## 🔄 Routes Upload & Import

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **POST** | `/api/upload/upload` | Upload 1 fichier (renommage auto) |
| **POST** | `/api/upload/upload-multiple` | Upload plusieurs fichiers |
| **POST** | `/api/upload/upload-and-import` ⭐ | Upload + Import automatique |
| **POST** | `/api/upload/import/enseignants` | Import enseignants depuis fichier uploadé |
| **POST** | `/api/upload/import/creneaux` | Import créneaux depuis fichier uploadé |
| **POST** | `/api/upload/import/voeux` | Import vœux depuis fichier uploadé |
| **GET** | `/api/upload/list-files` | Liste les fichiers dans uploads/ |

## 🎯 Routes Optimisation

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **POST** | `/api/affectations/run` | Lancer l'optimisation (avec diagnostic si infaisable) |
| **GET** | `/api/affectations/status/{session_id}` | Statut de l'optimisation |
| **GET** | `/api/affectations/stats/{session_id}` | Statistiques détaillées |
| **GET** | `/api/affectations/workload/{session_id}` | Charge de travail par enseignant |

## 📋 Routes Affectations (CRUD)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/affectations` | Liste toutes les affectations (filtrable) |
| **GET** | `/api/affectations/{id}` | Récupérer une affectation |
| **POST** | `/api/affectations` | Créer une affectation |
| **PUT** | `/api/affectations/{id}` | Modifier une affectation |
| **DELETE** | `/api/affectations/{id}` | Supprimer une affectation |
| **DELETE** | `/api/affectations/delete-all` | Supprimer toutes les affectations d'une session |
| **POST** | `/api/affectations/switch` | Permuter 2 enseignants |

## 👨‍🏫 Routes Enseignants

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/enseignants` | Liste tous les enseignants |
| **GET** | `/api/enseignants/{code}` | Récupérer un enseignant |
| **POST** | `/api/enseignants` | Créer un enseignant |
| **PUT** | `/api/enseignants/{code}` | Modifier un enseignant |
| **DELETE** | `/api/enseignants/{code}` | Supprimer un enseignant |

## 📅 Routes Créneaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/creneaux` | Liste tous les créneaux |
| **GET** | `/api/creneaux/{id}` | Récupérer un créneau |
| **POST** | `/api/creneaux` | Créer un créneau |
| **PUT** | `/api/creneaux/{id}` | Modifier un créneau |
| **DELETE** | `/api/creneaux/{id}` | Supprimer un créneau |

## 🙏 Routes Vœux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/voeux` | Liste tous les vœux |
| **GET** | `/api/voeux/{id}` | Récupérer un vœu |
| **POST** | `/api/voeux` | Créer un vœu |
| **PUT** | `/api/voeux/{id}` | Modifier un vœu |
| **DELETE** | `/api/voeux/{id}` | Supprimer un vœu |

## 📊 Routes Grades

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/grades` | Liste tous les grades |
| **GET** | `/api/grades/{code}` | Récupérer un grade |
| **POST** | `/api/grades` | Créer un grade |
| **PUT** | `/api/grades/{code}` | Modifier un grade |
| **DELETE** | `/api/grades/{code}` | Supprimer un grade |

## 🗓️ Routes Sessions

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/sessions` | Liste toutes les sessions |
| **GET** | `/api/sessions/{id}` | Récupérer une session |
| **POST** | `/api/sessions` | Créer une session |
| **PUT** | `/api/sessions/{id}` | Modifier une session |
| **DELETE** | `/api/sessions/{id}` | Supprimer une session |

## 🏫 Routes Salles par Créneau

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/salles-par-creneau` | Liste salles par créneau |
| **GET** | `/api/salles-par-creneau/{id}` | Récupérer une entrée |
| **POST** | `/api/salles-par-creneau` | Créer une entrée |
| **PUT** | `/api/salles-par-creneau/{id}` | Modifier une entrée |
| **DELETE** | `/api/salles-par-creneau/{id}` | Supprimer une entrée |

## 📈 Routes Quota Enseignants

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| **GET** | `/api/quota-enseignants` | Liste quotas par enseignant |
| **GET** | `/api/quota-enseignants/{id}` | Récupérer un quota |

---

## 🌟 Fonctionnalités Spéciales

### 🔍 Diagnostic d'Infaisabilité

Lorsque l'optimisation échoue (`status: "infeasible"`), l'API retourne automatiquement :

```json
{
  "success": false,
  "status": "infeasible",
  "infeasibility_diagnostic": {
    "is_feasible": false,
    "total_required": 350,
    "total_capacity": 300,
    "deficit": 50,
    "reasons": [
      {
        "type": "CAPACITE_INSUFFISANTE",
        "message": "Capacité insuffisante : 350 surveillances requises mais seulement 300 disponibles",
        "severity": "CRITICAL"
      }
    ],
    "grades_analysis": [...],
    "suggestions": [
      {
        "type": "AUGMENTER_QUOTAS",
        "description": "Augmenter tous les quotas à 8 surveillances/enseignant",
        "impact": "+100 surveillances",
        "feasible_after": true
      }
    ]
  }
}
```

### 🔄 Permutation Bidirectionnelle

Échanger complètement les affectations de 2 enseignants :

```bash
POST /api/affectations/switch
{
  "code1": 123,
  "code2": 456,
  "session_id": 1,
  "include_voeux": true
}
```

### 📁 Renommage Automatique

Tous les fichiers uploadés sont renommés selon leur type :
- `mon_fichier.xlsx` + type=`enseignants` → `enseignants.xlsx`
- `data.csv` + type=`creneaux` → `creneaux.csv`
- `preferences.xlsx` + type=`voeux` → `voeux.xlsx`

---

## 🚀 Workflow Complet

```bash
# 1. Créer une session
POST /api/sessions
{"libelle_session": "Session Janvier 2025", "date_debut": "2025-01-15", "date_fin": "2025-01-22"}

# 2. Upload + Import (en une requête)
POST /api/upload/upload-and-import
Form-data:
  - enseignants_file: fichier.xlsx
  - creneaux_file: fichier2.csv
  - voeux_file: fichier3.xlsx
  - id_session: 1

# 3. Lancer l'optimisation
POST /api/affectations/run
{"session_id": 1, "save": true}

# 4. Récupérer les résultats
GET /api/affectations?session_id=1
```

---

## 📝 Notes Importantes

- ✅ Toutes les routes retournent `{"success": true/false}`
- ✅ Les erreurs incluent des messages détaillés
- ✅ Support CORS configuré pour développement local
- ✅ Conversion automatique des types NumPy en JSON
- ✅ Mapping automatique des colonnes (détection intelligente)
- ✅ Génération automatique de `jour_seance` et `salle_par_creneau`
