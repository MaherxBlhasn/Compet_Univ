# Mise à jour de la table GRADE

## Changements apportés

La table `grade` a été mise à jour pour inclure le nom complet du grade en plus du code.

### Ancienne structure
```sql
CREATE TABLE grade (
    code_grade TEXT PRIMARY KEY,
    quota INTEGER NOT NULL
);
```

### Nouvelle structure
```sql
CREATE TABLE grade (
    code_grade TEXT PRIMARY KEY,
    grade TEXT NOT NULL,
    quota INTEGER NOT NULL
);
```

## Données selon l'image fournie

| Grade | Code_grade | Nombre de surveillances (quota) |
|-------|------------|--------------------------------|
| Professeur | PR | 4 |
| Maître de conférences | MC | 4 |
| Maître Assistant | MA | 7 |
| Assistant | AS | 8 |
| Assistant Contractuel | AC | 9 |
| Professeur Tronc Commun | PTC | 9 |
| Professeur d'enseignement secondaire | PES | 9 |
| Expert | EX | 3 |
| Vacataire | V | 4 |

## API CRUD mise à jour

### 1. GET /api/grades
Récupère tous les grades avec leur nom complet.

**Réponse:**
```json
[
  {
    "code_grade": "PR",
    "grade": "Professeur",
    "quota": 4
  },
  {
    "code_grade": "MC",
    "grade": "Maître de conférences",
    "quota": 4
  }
]
```

### 2. GET /api/grades/:code_grade
Récupère un grade spécifique.

**Exemple:** `GET /api/grades/PR`

**Réponse:**
```json
{
  "code_grade": "PR",
  "grade": "Professeur",
  "quota": 4
}
```

### 3. POST /api/grades
Crée un nouveau grade.

**Body:**
```json
{
  "code_grade": "PR",
  "grade": "Professeur",
  "quota": 4
}
```

**Réponse:**
```json
{
  "message": "Grade créé avec succès",
  "code_grade": "PR"
}
```

### 4. PUT /api/grades/:code_grade
Modifie un grade existant. Vous pouvez modifier le nom complet et/ou le quota.

**Exemple:** `PUT /api/grades/PR`

**Body (tous les champs sont optionnels):**
```json
{
  "grade": "Professeur Titulaire",
  "quota": 5
}
```

**Réponse:**
```json
{
  "message": "Grade modifié avec succès"
}
```

### 5. DELETE /api/grades/:code_grade
Supprime un grade.

**Exemple:** `DELETE /api/grades/PR`

**Réponse:**
```json
{
  "message": "Grade supprimé avec succès"
}
```

### 6. POST /api/grades/batch
Crée plusieurs grades en une seule requête.

**Body:**
```json
{
  "grades": [
    {
      "code_grade": "PR",
      "grade": "Professeur",
      "quota": 4
    },
    {
      "code_grade": "MC",
      "grade": "Maître de conférences",
      "quota": 4
    }
  ]
}
```

**Réponse:**
```json
{
  "message": "2 grades créés avec succès",
  "created": ["PR", "MC"],
  "errors": []
}
```

### 7. PUT /api/grades/batch
Modifie plusieurs grades en une seule requête.

**Body:**
```json
{
  "grades": [
    {
      "code_grade": "PR",
      "grade": "Professeur Titulaire",
      "quota": 5
    },
    {
      "code_grade": "MC",
      "quota": 6
    }
  ]
}
```

**Réponse:**
```json
{
  "message": "2 grades modifiés avec succès",
  "updated": ["PR", "MC"],
  "errors": []
}
```

## Migration de la base de données

Si vous avez déjà une base de données existante, exécutez le script de migration :

```bash
python database/migrate_add_grade_column.py
```

Ce script :
1. Vérifie si la colonne `grade` existe déjà
2. Crée une nouvelle table avec la structure mise à jour
3. Copie toutes les données existantes avec les noms complets
4. Remplace l'ancienne table par la nouvelle

## Compatibilité

- ✅ Les enseignants existants restent liés à leurs grades via `grade_code_ens`
- ✅ Toutes les contraintes de clé étrangère sont préservées
- ✅ Les quotas existants sont conservés
- ✅ L'API REST est rétrocompatible (les anciennes requêtes fonctionnent toujours)
