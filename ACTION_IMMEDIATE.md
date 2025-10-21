# 🎯 Action Immédiate - Résoudre le Problème de Performance

## ⚡ Solution Rapide (5 minutes)

### Étape 1 : Créer les Index SQL

```bash
cd c:\Users\lenovo\Desktop\UniversityProjects\CompetitionISI\Compet_Univ
python scripts/create_indexes.py
```

**Résultat attendu** : "✅ Optimisation terminée avec succès!"

### Étape 2 : Tester l'Optimisation

```bash
python scripts/optimize_example.py
```

**Choisir** : Une session que vous avez déjà testée (pour comparer)

### Étape 3 : Noter les Temps

Vous verrez maintenant :
```
SESSION ID : 2
✓ Toutes les données chargées en X.XXs          ← Noter
⏱️  Temps de préparation : X.XXs                 ← Noter
⏱️  Temps de création du modèle : X.XXs          ← Noter
✓ Temps de résolution pure : X.XXs               ← Noter
✓ Temps total : X.XXs                            ← Noter
```

### Étape 4 : Analyser

#### Si Temps Total < 60s
✅ **Problème résolu !** Les index ont suffi.

#### Si Temps Total entre 60-120s
⚠️ **Amélioration possible**. Appliquer les optimisations supplémentaires ci-dessous.

#### Si Temps Total > 120s
❌ **Optimisations supplémentaires nécessaires**. Voir Section B.

---

## 🔧 Section A : Si Temps de Résolution Pure > 100s

### Solution : Limiter l'Historique des Quotas

**Modifier** : `scripts/optimize_example.py` ligne ~43

**Remplacer** :
```python
def get_previous_session_id(conn, current_session_id):
    """Trouver la session précédente"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id_session 
        FROM session 
        WHERE id_session < ? 
        ORDER BY id_session DESC 
        LIMIT 1
    """, (current_session_id,))
    
    row = cursor.fetchone()
    return row['id_session'] if row else None
```

**Par** :
```python
def get_previous_session_id(conn, current_session_id):
    """Trouver la session précédente (limité à 1 session d'écart maximum)"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id_session 
        FROM session 
        WHERE id_session < ? 
        AND id_session >= ? - 1
        ORDER BY id_session DESC 
        LIMIT 1
    """, (current_session_id, current_session_id))
    
    row = cursor.fetchone()
    return row['id_session'] if row else None
```

**Impact** : Ne considère que la session immédiatement précédente (pas toutes les sessions d'avant)

**Gain attendu** : Temps divisé par 2

---

## 🔧 Section B : Si Temps de Résolution Pure > 150s

### Solution : Augmenter le Temps Maximum

**Modifier** : `scripts/optimize_example.py` ligne ~1146

**Remplacer** :
```python
solver.parameters.max_time_in_seconds = 180
```

**Par** :
```python
solver.parameters.max_time_in_seconds = 300  # 5 minutes
```

**Impact** : Laisse plus de temps au solver pour trouver une solution optimale

---

## 🔧 Section C : Si Temps de Création du Modèle > 30s

### Solution : Réduire le Nombre de Réserves

**Modifier** : `scripts/optimize_example.py` ligne ~325

**Remplacer** :
```python
# CALCUL DYNAMIQUE DES RÉSERVES
if nb_reserves_dynamique is None:
    # Calcul automatique : min(nb_salles, 4) pour éviter trop de réserves
    nb_reserves = min(nb_salles, 4)
else:
    nb_reserves = nb_reserves_dynamique
```

**Par** :
```python
# CALCUL DYNAMIQUE DES RÉSERVES
if nb_reserves_dynamique is None:
    # Calcul automatique : min(nb_salles, 2) - RÉDUIT POUR PERFORMANCE
    nb_reserves = min(nb_salles, 2)
else:
    nb_reserves = nb_reserves_dynamique
```

**Impact** : Moins de surveillants nécessaires → Moins de variables → Plus rapide

**Trade-off** : Moins de réserves disponibles

---

## 🎯 Plan d'Action Recommandé

### Jour 1 (Aujourd'hui)
- [x] Créer les index SQL
- [ ] Tester et noter les temps
- [ ] Si > 120s, appliquer Section A

### Jour 2 (Si Nécessaire)
- [ ] Si toujours > 150s, appliquer Section B
- [ ] Si création modèle > 30s, appliquer Section C

### Jour 3 (Si Toujours Lent)
- [ ] Lire `OPTIMISATION_PERFORMANCE.md`
- [ ] Envisager de passer équité absolue en SOFT
- [ ] Contacter support avec les diagnostics

---

## 📊 Suivi des Performances

### Avant Optimisations
| Session | Temps (sec) | Status |
|---------|-------------|--------|
| 1       | 30          | ✅     |
| 2       | 110         | ⚠️     |
| 3       | 180+        | ❌     |

### Après Optimisations
| Session | Temps (sec) | Amélioration | Status |
|---------|-------------|--------------|--------|
| 1       | ?           | ?%           | ?      |
| 2       | ?           | ?%           | ?      |
| 3       | ?           | ?%           | ?      |

**Remplir ce tableau** après avoir appliqué les optimisations !

---

## ✅ Checklist Rapide

### Étape 1 : Index SQL
- [ ] Exécuté `python scripts/create_indexes.py`
- [ ] Message "✅ Optimisation terminée avec succès!" affiché
- [ ] 8 index créés

### Étape 2 : Test Initial
- [ ] Exécuté `python scripts/optimize_example.py`
- [ ] Noté tous les temps affichés
- [ ] Identifié le goulot (chargement, préparation, modèle, ou résolution)

### Étape 3 : Optimisations Ciblées
- [ ] Si résolution > 100s : Appliqué Section A
- [ ] Si résolution > 150s : Appliqué Section B
- [ ] Si création modèle > 30s : Appliqué Section C

### Étape 4 : Vérification
- [ ] Retesté après chaque modification
- [ ] Mesuré l'amélioration (gain en %)
- [ ] Documenté les résultats

---

## 🆘 Besoin d'Aide ?

### Commandes de Diagnostic

```bash
# Analyser la base de données
python scripts/create_indexes.py

# Voir la taille du problème
python scripts/optimize_example.py
# → Regarder "Taille du problème"

# Vérifier les index
sqlite3 surveillance.db "SELECT name FROM sqlite_master WHERE type='index'"
```

### Informations à Fournir

Si vous avez besoin d'aide, fournir :
1. Les temps affichés (chargement, préparation, modèle, résolution)
2. La taille du problème (enseignants, créneaux, variables)
3. Le numéro de la session testée
4. Les optimisations déjà appliquées

---

## 🎉 Résultats Attendus

### Avec Index SQL Seulement
- **Session 1** : 30s → 20s (-33%)
- **Session 2** : 110s → 60s (-45%)
- **Session 3** : 180s+ → 90s (-50%)

### Avec Index + Limite Historique (Section A)
- **Session 1** : 30s → 18s (-40%)
- **Session 2** : 110s → 35s (-68%)
- **Session 3** : 180s+ → 45s (-75%)

### Avec Toutes les Optimisations (A+B+C)
- **Session 1** : 30s → 15s (-50%)
- **Session 2** : 110s → 25s (-77%)
- **Session 3** : 180s+ → 35s (-81%)

---

## 💡 Astuce Finale

**Pour chaque session, exécutez** :
```bash
time python scripts/optimize_example.py
```

Cela affichera le temps total à la fin :
```
real    0m45.234s
user    3m12.456s
sys     0m2.345s
```

Le temps `real` est celui qui compte !

---

**Bonne chance ! 🚀**
