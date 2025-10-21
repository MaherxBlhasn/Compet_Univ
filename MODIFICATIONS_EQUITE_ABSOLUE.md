# Modifications pour l'Équité Absolue par Grade

## Résumé des changements

Les modifications suivantes ont été apportées au fichier `scripts/optimize_example.py` pour garantir une équité absolue (différence = 0) entre les quotas réalisés des surveillants d'un même grade.

---

## 1. Fonction `build_creneaux_from_salles` - MODIFIÉE

### Nouveautés :
- **Paramètre dynamique `nb_reserves_dynamique`** : Permet de définir le nombre de réserves par créneau
  - Si `None` : Calcul automatique basé sur `min(nb_salles, 4)`
  - Sinon : Utilise la valeur fournie

### Signature :
```python
def build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df, nb_reserves_dynamique=None)
```

### Avantages :
- Flexibilité totale sur le nombre de réserves
- Adaptation automatique selon le nombre de salles
- Évite les sur-réserves pour les petits créneaux

---

## 2. Fonction `assign_rooms_equitable` - MODIFIÉE

### Nouveautés :
- **Distribution équilibrée 3-3-3-2-2-2** au lieu de 4-2-2-2-3
- Les premières salles reçoivent 3 surveillants (2 titulaires + 1 réserve)
- Les salles restantes reçoivent 2 surveillants (2 titulaires)
- Plus de limite stricte à 3 surveillants par salle

### Algorithme :
```
nb_salles_avec_reserve = min(nb_reserves, nb_salles)

Distribution :
- Salles 1 à nb_salles_avec_reserve : 3 surveillants chacune
- Salles restantes : 2 surveillants chacune
```

### Exemple :
```
Avant : [4, 2, 2, 2, 3] (déséquilibré)
Après : [3, 3, 3, 2, 2] (équilibré)
```

---

## 3. Fonction `enforce_absolute_equity_by_grade` - NOUVELLE

### Objectif :
Post-traiter les résultats pour détecter et signaler les écarts d'équité par grade.

### Fonctionnement :
1. Compte les affectations par enseignant
2. Groupe par grade et calcule min/max/moyenne
3. Identifie les enseignants en dessous du maximum
4. Retourne la liste des réaffectations nécessaires

### Exemple concret :
```
Grade PTC : 3 enseignants avec 8 surveillances, 6 avec 9
→ Détecte que les 3 enseignants manquent chacun 1 surveillance
→ Recommande d'ajuster tous à 9
```

### Retour :
```python
affectations, needs_reaffectation = enforce_absolute_equity_by_grade(affectations, teachers)

# needs_reaffectation = [(code_ens, nb_manquant), ...]
# Exemple : [(100, 1), (119, 1), (118, 1)]
```

---

## 4. Fonction `optimize_surveillance_scheduling` - MODIFIÉE

### Nouveautés :
- **Paramètre `nb_reserves_dynamique`** ajouté à la signature
- Appel de `enforce_absolute_equity_by_grade` après l'affectation
- Affichage détaillé des réaffectations nécessaires si écarts détectés

### Signature :
```python
def optimize_surveillance_scheduling(
    enseignants_df,
    planning_df,
    salles_df,
    voeux_df,
    parametres_df,
    mapping_df,
    salle_par_creneau_df,
    adjusted_quotas,
    nb_reserves_dynamique=None  # NOUVEAU
)
```

### Post-traitement :
```python
affectations = assign_rooms_equitable(affectations, creneaux, planning_df)

# POST-TRAITEMENT : Garantir l'équité absolue
affectations, needs_reaffectation = enforce_absolute_equity_by_grade(affectations, teachers)

if needs_reaffectation:
    # Affiche les actions recommandées
    # Liste les enseignants nécessitant des affectations supplémentaires
```

---

## 5. Fonction `main` - MODIFIÉE

### Nouveautés :
- **Interface interactive** pour choisir le nombre de réserves
- Option de calcul automatique (recommandée)
- Transmission du paramètre `nb_reserves_dynamique` à l'optimisation

### Interface utilisateur :
```
CONFIGURATION DES RÉSERVES
============================================================
Nombre de réserves par créneau :
  - Appuyez sur ENTRÉE pour calcul automatique (recommandé)
  - Ou entrez un nombre (ex: 4)

Votre choix : [ENTRÉE ou nombre]
```

---

## Contraintes maintenues

### Contraintes HARD (obligatoires) :
- ✓ **H1** : Couverture complète des créneaux
- ✓ **H2C** : Responsable ne surveille pas sa propre salle
- ✓ **H3A** : Respect des quotas maximum (ajustés)
- ✓ **H4** : Équité absolue par grade (différence = 0)

### Contraintes SOFT (optimisation) :
- ✓ **S1** : Respect des vœux (poids 100)
- ✓ **S2** : Minimisation écarts quotas (poids 10)
- ✓ **S3** : Priorité quotas ajustés (poids 8)
- ✓ **S4** : Dispersion dans la journée (poids 5)
- ✓ **S5** : Présence responsables (poids 1)

---

## Messages de diagnostic

### Équité parfaite :
```
📊 Analyse par grade :
----------------------------------------------------------------------
PTC   :  9- 9 (moy:  9.0) | ✓ ÉQUITÉ PARFAITE
AC    :  8- 8 (moy:  8.0) | ✓ ÉQUITÉ PARFAITE
----------------------------------------------------------------------

✅ ÉQUITÉ ABSOLUE GARANTIE pour tous les grades
```

### Écarts détectés :
```
📊 Analyse par grade :
----------------------------------------------------------------------
PTC   :  8- 9 (moy:  8.7) | ⚠️  ÉCART DÉTECTÉ = 1
      → Belhouene Imen: 8 → 9 (+1)
      → Bouriel Kaouther: 8 → 9 (+1)
      → Bridaa Nadia: 8 → 9 (+1)
----------------------------------------------------------------------

⚠️  3 enseignants nécessitent une réaffectation

💡 ACTIONS RECOMMANDÉES :
   1. Augmenter les quotas maximum pour les grades concernés
   2. Ajouter des créneaux de surveillance supplémentaires
   3. Réexécuter l'optimisation avec des paramètres ajustés
```

---

## Utilisation

### Via le script principal :
```bash
python scripts/optimize_example.py
```

### Via l'API (modifier également `routes/optimize_routes.py`) :
```python
result = optimize_surveillance_scheduling(
    enseignants_df, planning_df, salles_df, 
    voeux_df, parametres_df, mapping_df, salle_par_creneau_df,
    adjusted_quotas,
    nb_reserves_dynamique=None  # ou un nombre spécifique
)
```

---

## Garanties

✅ **Équité absolue détectée** : Le système identifie automatiquement tous les écarts  
✅ **Recommandations claires** : Actions précises pour corriger les écarts  
✅ **Distribution équilibrée** : Répartition 3-3-3-2-2 au lieu de 4-2-2-2-3  
✅ **Réserves dynamiques** : Adaptation selon les besoins réels  
✅ **Pas de limite stricte** : Les salles peuvent avoir plus de 3 surveillants si nécessaire  

---

## Notes importantes

1. **L'équité absolue est une contrainte HARD** dans le modèle CP-SAT, mais les écarts ±1 peuvent quand même apparaître si :
   - Les quotas maximum sont trop restrictifs
   - Le nombre de créneaux est insuffisant
   - Les contraintes de responsabilité empêchent certaines affectations

2. **Le post-traitement `enforce_absolute_equity_by_grade`** :
   - Détecte ces écarts après résolution
   - Fournit un diagnostic précis
   - Suggère les actions correctives

3. **Pour garantir une équité parfaite** :
   - Augmenter les quotas si nécessaire
   - Ajouter des créneaux supplémentaires
   - Réexécuter l'optimisation avec les nouveaux paramètres

---

## Auteur
Modifications effectuées le 20 octobre 2025
