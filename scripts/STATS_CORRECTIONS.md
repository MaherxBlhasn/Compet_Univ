# Corrections des Statistiques de Surveillance

## Changements apportés dans `surveillance_stats.py`

### 1. **Taux de Couverture** ✅

**Avant :** Le taux de couverture vérifiait si chaque créneau avait exactement le nombre requis de surveillants.

**Après :** Le taux de couverture vérifie maintenant que **toutes les salles ont au minimum 2 surveillants**.

#### Nouvelle logique :
```python
def _compute_couverture_stats(self):
    """Analyser la couverture des créneaux - toutes les salles doivent avoir minimum 2 surveillants"""
    
    # Regrouper les affectations par créneau et salle
    couverture_par_salle = defaultdict(lambda: defaultdict(int))
    
    for _, aff in self.aff.iterrows():
        cid = aff['creneau_id']
        salle = aff['salle']
        if pd.notna(cid) and pd.notna(salle):
            couverture_par_salle[cid][salle] += 1
    
    # Compter les salles bien couvertes (>= 2) vs sous-couvertes (< 2)
    total_salles = 0
    salles_bien_couvertes = 0  # >= 2 surveillants
    salles_sous_couvertes = 0  # < 2 surveillants
    
    for cid in couverture_par_salle:
        for salle, nb_surveillants in couverture_par_salle[cid].items():
            total_salles += 1
            if nb_surveillants >= 2:
                salles_bien_couvertes += 1
            else:
                salles_sous_couvertes += 1
```

#### Affichage :
```
[5] COUVERTURE DES CRENEAUX
    Salles totales : 150
    Salles avec >= 2 surveillants : 148 (98.7%)
    Salles avec < 2 surveillants : 2
```

---

### 2. **Présence des Responsables** ✅

**Avant :** La présence des responsables était calculée pour tous les enseignants responsables de salles, qu'ils participent ou non aux surveillances.

**Après :** La présence des responsables est maintenant calculée **uniquement pour les enseignants avec `participe_surveillance = 1`**.

#### Nouvelle logique :
```python
def _compute_responsable_stats(self):
    """Analyser la disponibilité des responsables (uniquement ceux avec participe_surveillance=1)"""
    
    salle_responsable = {}
    for _, row in planning_df_copy.iterrows():
        date = row['dateExam']
        h_debut = row['h_debut_parsed']
        salle = row['cod_salle']
        responsable = row['enseignant']
        
        if pd.notna(date) and pd.notna(h_debut) and pd.notna(salle) and pd.notna(responsable):
            try:
                responsable = int(responsable)
                # ⭐ Vérifier que le responsable participe aux surveillances
                if responsable in self.teachers and self.teachers[responsable]['participe']:
                    key = (date, h_debut, salle)
                    salle_responsable[key] = responsable
            except (ValueError, TypeError):
                continue
```

#### Affichage :
```
[3] RESPONSABLES DE SALLES
    Responsabilités à couvrir : 120 (participe_surveillance=1)
    Responsables présents : 95 (79.2%)
    Responsables absents : 25 (20.8%)
```

---

## Résumé des Modifications

| Statistique | Avant | Après |
|------------|-------|-------|
| **Couverture** | Créneaux couverts exactement | Salles avec >= 2 surveillants |
| **Responsables** | Tous les responsables | Uniquement ceux avec `participe_surveillance=1` |

---

## Impact sur le Résumé Global

Le résumé global affiche maintenant :
```
======================================================================
RÉSUMÉ GLOBAL
======================================================================

✓ VOEUX         : 100.0% (436/436)
✓ DISPERSION    :   1 prof espacées / 225 consécutives
✓ RESPONSABLES  :  79.2% présents (95/120 avec participe=1)
✓ ÉQUITÉ        :  90.0% (9/10 grades)
✓ COUVERTURE    :  98.7% (148/150 salles avec >=2 surveillants)
```

---

## Fichiers Modifiés

- ✅ `scripts/surveillance_stats.py`
  - Fonction `_compute_couverture_stats()` : Nouvelle logique de couverture par salle
  - Fonction `_compute_responsable_stats()` : Filtre sur `participe_surveillance=1`
  - Fonction `_print_summary()` : Affichage mis à jour

---

## Test

Pour tester les changements, lancez l'optimisation :
```bash
python scripts/optimize_example.py
```

Ou via l'API :
```bash
POST /api/optimize/run
```

Les nouvelles statistiques seront affichées automatiquement après l'optimisation.
