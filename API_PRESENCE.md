# API Présence des Responsables - Documentation

## Vue d'ensemble

Cette API permet de gérer et consulter les informations de présence/absence des enseignants responsables d'examens. Elle se base sur la table `responsable_absent_jour_examen` qui est automatiquement remplie après chaque optimisation ou création d'affectation.

**Base URL**: `/api/presence`

---

## Endpoints

### 1. GET `/api/presence` - Récupérer tous les responsables absents

Retourne la liste complète de tous les responsables absents, toutes sessions confondues.

**Query Parameters** (optionnels):
- `session_id` (int): Filtrer par session
- `participe_surveillance` (int): Filtrer par participation aux surveillances (0 ou 1)

**Exemple de requête**:
```bash
# Tous les responsables absents
GET http://127.0.0.1:5000/api/presence

# Filtrer par session
GET http://127.0.0.1:5000/api/presence?session_id=4

# Filtrer par participation aux surveillances
GET http://127.0.0.1:5000/api/presence?participe_surveillance=1

# Filtres combinés
GET http://127.0.0.1:5000/api/presence?session_id=4&participe_surveillance=1
```

**Réponse (200 OK)**:
```json
{
  "count": 3,
  "statistiques": {
    "total_responsables_absents": 3,
    "total_jours_absents": 5,
    "total_creneaux_absents": 8
  },
  "data": [
    {
      "id": 1,
      "id_session": 4,
      "libelle_session": "Session Janvier 2025",
      "code_smartex_ens": 12345,
      "nom": "DUPONT",
      "prenom": "Jean",
      "grade_code": "PA",
      "participe_surveillance": true,
      "nbre_jours_absents": 2,
      "nbre_creneaux_absents": 3,
      "nbre_total_jours_responsable": 5,
      "nbre_total_creneaux_responsable": 10,
      "dates_absentes": ["2025-01-15", "2025-01-17"],
      "taux_presence_jours": 60.0,
      "taux_presence_creneaux": 70.0
    },
    ...
  ]
}
```

---

### 2. GET `/api/presence/session/<id_session>` - Responsables absents par session

Retourne tous les responsables absents pour une session spécifique avec statistiques détaillées.

**Paramètres**:
- `id_session` (int, required): ID de la session

**Exemple de requête**:
```bash
GET http://127.0.0.1:5000/api/presence/session/4
```

**Réponse (200 OK)**:
```json
{
  "session_id": 4,
  "session_libelle": "Session Janvier 2025",
  "count": 3,
  "statistiques": {
    "total_responsables_absents": 3,
    "total_enseignants_surveillants": 89,
    "total_jours_absents": 5,
    "total_creneaux_absents": 8,
    "taux_responsables_presents": 96.63
  },
  "data": [
    {
      "id": 1,
      "id_session": 4,
      "code_smartex_ens": 12345,
      "nom": "DUPONT",
      "prenom": "Jean",
      "grade_code": "PA",
      "participe_surveillance": true,
      "nbre_jours_absents": 2,
      "nbre_creneaux_absents": 3,
      "nbre_total_jours_responsable": 5,
      "nbre_total_creneaux_responsable": 10,
      "dates_absentes": ["2025-01-15", "2025-01-17"],
      "taux_presence_jours": 60.0,
      "taux_presence_creneaux": 70.0
    },
    ...
  ]
}
```

**Réponse (404 Not Found)**:
```json
{
  "error": "Session non trouvée"
}
```

---

### 3. GET `/api/presence/enseignant/<code_smartex>` - Historique d'un enseignant

Retourne l'historique complet des absences d'un enseignant à travers toutes les sessions.

**Paramètres**:
- `code_smartex` (int, required): Code SmartEx de l'enseignant

**Exemple de requête**:
```bash
GET http://127.0.0.1:5000/api/presence/enseignant/12345
```

**Réponse (200 OK)**:
```json
{
  "enseignant": {
    "code_smartex_ens": 12345,
    "nom": "DUPONT",
    "prenom": "Jean",
    "grade": "PA",
    "participe_surveillance": true
  },
  "count": 2,
  "statistiques": {
    "total_sessions_avec_absences": 2,
    "total_jours_absents": 4,
    "total_creneaux_absents": 7,
    "total_jours_responsable": 10,
    "total_creneaux_responsable": 20,
    "taux_presence_global_jours": 60.0,
    "taux_presence_global_creneaux": 65.0
  },
  "data": [
    {
      "id": 1,
      "id_session": 4,
      "libelle_session": "Session Janvier 2025",
      "nbre_jours_absents": 2,
      "nbre_creneaux_absents": 3,
      "nbre_total_jours_responsable": 5,
      "nbre_total_creneaux_responsable": 10,
      "dates_absentes": ["2025-01-15", "2025-01-17"],
      "taux_presence_jours": 60.0,
      "taux_presence_creneaux": 70.0
    },
    {
      "id": 5,
      "id_session": 5,
      "libelle_session": "Session Juin 2025",
      "nbre_jours_absents": 2,
      "nbre_creneaux_absents": 4,
      "nbre_total_jours_responsable": 5,
      "nbre_total_creneaux_responsable": 10,
      "dates_absentes": ["2025-06-10", "2025-06-12"],
      "taux_presence_jours": 60.0,
      "taux_presence_creneaux": 60.0
    }
  ]
}
```

**Réponse (404 Not Found)**:
```json
{
  "error": "Enseignant non trouvé"
}
```

---

## Structure des données

### Objet Responsable Absent

```typescript
{
  id: number;                              // ID unique dans la table
  id_session: number;                      // ID de la session
  libelle_session?: string;                // Nom de la session (si jointure)
  code_smartex_ens: number;                // Code SmartEx de l'enseignant
  nom: string;                             // Nom de famille
  prenom: string;                          // Prénom
  grade_code: string;                      // Code du grade (PA, MC, MA, etc.)
  participe_surveillance: boolean;         // Participe aux surveillances
  nbre_jours_absents: number;              // Nombre de jours absents
  nbre_creneaux_absents: number;           // Nombre de créneaux absents
  nbre_total_jours_responsable: number;    // Total de jours où responsable
  nbre_total_creneaux_responsable: number; // Total de créneaux où responsable
  dates_absentes: string[];                // Liste des dates absentes (array)
  taux_presence_jours: number;             // % présence (jours) = 100 - (absents/total × 100)
  taux_presence_creneaux: number;          // % présence (créneaux) = 100 - (absents/total × 100)
}
```

---

## Exemples d'utilisation

### Python
```python
import requests

BASE_URL = "http://127.0.0.1:5000/api/presence"

# 1. Récupérer tous les responsables absents
response = requests.get(BASE_URL)
data = response.json()
print(f"Total: {data['count']} responsables absents")

# 2. Filtrer par session
response = requests.get(f"{BASE_URL}?session_id=4")
data = response.json()

# 3. Récupérer pour une session spécifique
response = requests.get(f"{BASE_URL}/session/4")
data = response.json()
print(f"Session: {data['session_libelle']}")
print(f"Taux présence: {data['statistiques']['taux_responsables_presents']}%")

# 4. Historique d'un enseignant
response = requests.get(f"{BASE_URL}/enseignant/12345")
data = response.json()
print(f"Enseignant: {data['enseignant']['nom']} {data['enseignant']['prenom']}")
print(f"Taux présence global: {data['statistiques']['taux_presence_global_jours']}%")
```

### cURL
```bash
# GET ALL
curl http://127.0.0.1:5000/api/presence

# GET par session
curl http://127.0.0.1:5000/api/presence/session/4

# GET par enseignant
curl http://127.0.0.1:5000/api/presence/enseignant/12345

# GET avec filtres
curl "http://127.0.0.1:5000/api/presence?session_id=4&participe_surveillance=1"
```

### JavaScript (Fetch API)
```javascript
// GET ALL
const response = await fetch('http://127.0.0.1:5000/api/presence');
const data = await response.json();
console.log(`Total: ${data.count} responsables absents`);

// GET par session
const sessionData = await fetch('http://127.0.0.1:5000/api/presence/session/4')
  .then(res => res.json());
console.log(`Taux présence: ${sessionData.statistiques.taux_responsables_presents}%`);

// GET par enseignant
const ensData = await fetch('http://127.0.0.1:5000/api/presence/enseignant/12345')
  .then(res => res.json());
console.log(`Sessions avec absences: ${ensData.statistiques.total_sessions_avec_absences}`);
```

---

## Notes importantes

### 🔄 Mise à jour automatique
La table `responsable_absent_jour_examen` est **automatiquement remplie** après :
- Exécution de l'optimisation (`POST /api/optimize/session/<id>`)
- Création d'affectations manuelles

### 📊 Calculs des taux
- **Taux de présence (jours)** = `(total_jours - jours_absents) / total_jours × 100`
- **Taux de présence (créneaux)** = `(total_créneaux - créneaux_absents) / total_créneaux × 100`

### 🎯 Définition d'absence
Un responsable est considéré **absent** pour un jour si :
- Il est responsable d'au moins un examen ce jour-là (champ `enseignant` dans `creneau`)
- Il n'a **aucune affectation de surveillance** sur ce jour (aucun créneau ce jour dans `affectation`)

### ⚠️ Filtres de participation
Le champ `participe_surveillance` permet de différencier :
- `participe_surveillance = 1` : Enseignants qui participent normalement aux surveillances
- `participe_surveillance = 0` : Enseignants exemptés de surveillance (responsables administratifs, etc.)

---

## Testing

Un script de test complet est disponible : `scripts/test_presence_api.py`

```bash
# Démarrer le serveur Flask
python app.py

# Dans un autre terminal, exécuter les tests
python scripts/test_presence_api.py
```

Le script teste :
- ✅ GET ALL sans filtres
- ✅ GET ALL avec filtres (session_id, participe_surveillance)
- ✅ GET par session
- ✅ GET par enseignant
- ✅ Gestion des erreurs (404)

---

## Codes d'erreur

| Code | Description |
|------|-------------|
| 200  | Succès |
| 404  | Ressource non trouvée (session ou enseignant) |
| 500  | Erreur serveur interne |

---

## Intégration avec Statistics API

Cette API complète l'endpoint `/api/statistics/session/<id>` qui retourne un résumé simplifié :

```json
{
  "responsables_salles": {
    "responsables_absents_count": 3,
    "total_enseignants_surveillants": 89,
    "taux_surveillants_responsable_present": 96.63
  }
}
```

Pour les détails complets (noms, dates, historique), utilisez `/api/presence`.
