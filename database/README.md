# Dossier Database

Ce dossier contient les modules liés à la gestion de la base de données.

## Fichiers

- **create_database.py** : Script de création de la base de données et des tables
- **database.py** : Fonctions d'initialisation et de connexion à la base de données

## Utilisation

```python
from database import init_db, get_db

# Initialiser la base de données
init_db(app)

# Obtenir une connexion
conn = get_db()
```
