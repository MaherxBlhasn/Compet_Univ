# Module d'Aide à la Décision

## Vue d'ensemble
Module intelligent pour calculer automatiquement les quotas optimaux de surveillance par grade académique.

## Logique & Algorithmes

### 1. Calcul des Surveillances Nécessaires
```
surveillances_base = Σ(nb_surveillants par salle par créneau)
surveillances_totales = surveillances_base × (1 + marge_absences)
```
- **Marge absences**: 15% par défaut (configurable 0-50%)

### 2. Hiérarchie des Grades (4 niveaux)
```
Niveau 1: PR, MC, V     → quota_base
Niveau 2: MA            → quota_base + 3
Niveau 3: AS, EX        → quota_base + 6  
Niveau 4: AC, PTC, PES  → quota_base + 9
```
- **Formule**: `quota(niveau) = quota_base + (niveau - 1) × min_difference`
- **min_difference**: 3 par défaut (différence entre niveaux)

### 3. Ajustement Automatique
Si capacité insuffisante:
```python
déficit = surveillances_requises - capacité_actuelle
while déficit > 0:
    quota_tous_grades += 1
    recalculer_capacité()
```

### 4. Calcul Maximum de Voeux Autorisés
```
max_voeux = nb_creneaux_total - quota_grade - marge_sécurité
marge_sécurité = ⌈quota × 0.5⌉
```
**Logique inverse**: Plus le quota est élevé → MOINS de voeux autorisés (besoin de plus de disponibilité)

**Exemple**:
- PTC (quota=12): max 293 voeux sur 311 créneaux (94.2%)
- PR (quota=2): max 308 voeux sur 311 créneaux (99.0%)

## Input

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `session_id` | int | - | ID de la session d'examen |
| `absence_margin` | float | 0.15 | Marge pour absences (15%) |
| `min_difference` | int | 3 | Différence minimale entre niveaux |
| `max_voeux_ratio` | float | 0.70 | Ratio limite pour calcul voeux |

**Données DB requises**:
- `enseignant` (code, grade)
- `grade` (code, quota actuel)
- `creneau` (tous les créneaux)
- `salle_par_creneau` (nb surveillants par salle)
- `voeu` (souhaits des enseignants)

## Output

### Structure JSON
```json
{
  "session_id": 1,
  "surveillances_base": 622,
  "surveillances_totales": 716,
  "quotas_by_grade": {
    "PR": {"quota": 2, "count": 10, "total": 20},
    "MA": {"quota": 5, "count": 57, "total": 285},
    "AC": {"quota": 12, "count": 9, "total": 108}
  },
  "max_voeux_allowance": {
    "PR": 308,
    "MA": 303,
    "AC": 293
  },
  "individual_quotas": [
    {
      "code_smartex_ens": 1,
      "nom_ens": "Zagrouba",
      "prenom_ens": "Ezzedine",
      "grade_code_ens": "PR",
      "quota_propose": 2
    }
  ],
  "nb_enseignants": 126,
  "nb_creneaux": 311,
  "parameters": {...}
}
```

### Fichiers Générés
- `quotas_proposes_session_X.csv`: Quotas individuels par enseignant
- `decision_summary_session_X.json`: Résumé complet des recommandations

## API Routes

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/recommendations/<session_id>` | GET | Générer recommandations |
| `/compare/<session_id>` | GET | Comparer proposé vs actuel |
| `/apply/<session_id>` | POST | Appliquer les quotas |
| `/current-quotas` | GET | Obtenir quotas actuels |
| `/statistics/<session_id>` | GET | Statistiques détaillées |
| `/parameters-info` | GET | Info sur paramètres |

## Exemple d'utilisation

```bash
# Générer recommandations
curl "http://localhost:5000/api/decision-support/recommendations/1?absence_margin=0.15&min_difference=3"

# Comparer avec quotas actuels
curl "http://localhost:5000/api/decision-support/compare/1"

# Appliquer les recommandations
curl -X POST "http://localhost:5000/api/decision-support/apply/1"
```

## Garanties

✅ **Faisabilité**: Capacité totale ≥ surveillances requises  
✅ **Hiérarchie**: Quotas respectent l'ordre des grades  
✅ **Disponibilité**: Chaque enseignant a assez de créneaux disponibles (311 - quota - marge ≥ 0)  
✅ **Flexibilité**: Paramètres configurables pour ajuster selon besoins

## Fichier Principal
`scripts/decision_support_module.py` - Classe `DecisionSupportModule`
