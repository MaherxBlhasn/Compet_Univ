# API Endpoints - PDFs de Présence des Responsables

## 📚 Documentation Complète

---

## 1️⃣ Générer les PDFs

### Endpoint
```
GET /api/affectations/generate_presences_responsables/<session_id>
```

### Description
Génère les PDFs de présence pour tous les enseignants responsables de la session.
Les enseignants sont récupérés depuis la table `responsable_absent_jour_examen`.

### Paramètres
- `session_id` (int, path): ID de la session

### Réponse Succès (200)
```json
{
  "message": "PDF de présence des responsables générés avec succès pour la session 4",
  "nombre_responsables": 3,
  "dossier": "results/presences_responsables/session_4"
}
```

### Réponse Erreur (404)
```json
{
  "message": "Aucun responsable absent trouvé dans la table pour la session 4"
}
```

### Exemple
```bash
curl -X GET http://127.0.0.1:5000/api/affectations/generate_presences_responsables/4
```

---

## 2️⃣ Lister les PDFs disponibles

### Endpoint
```
GET /api/affectations/presences_responsables/list/<session_id>
```

### Description
Retourne la liste de tous les PDFs de présence générés pour une session.

### Paramètres
- `session_id` (int, path): ID de la session

### Réponse Succès (200)
```json
{
  "success": true,
  "session_id": 4,
  "count": 3,
  "files": [
    {
      "filename": "presence_responsable_DUPONT_Jean_4.pdf",
      "size": 45678,
      "size_mb": 0.04,
      "created": "2025-10-18 14:30:25",
      "download_url": "/api/affectations/presences_responsables/download/4/presence_responsable_DUPONT_Jean_4.pdf"
    },
    {
      "filename": "presence_responsable_MARTIN_Marie_4.pdf",
      "size": 46234,
      "size_mb": 0.04,
      "created": "2025-10-18 14:30:26",
      "download_url": "/api/affectations/presences_responsables/download/4/presence_responsable_MARTIN_Marie_4.pdf"
    },
    {
      "filename": "presence_responsable_BERNARD_Paul_4.pdf",
      "size": 45890,
      "size_mb": 0.04,
      "created": "2025-10-18 14:30:27",
      "download_url": "/api/affectations/presences_responsables/download/4/presence_responsable_BERNARD_Paul_4.pdf"
    }
  ]
}
```

### Réponse Erreur (404)
```json
{
  "success": false,
  "message": "Aucun PDF de présence trouvé pour la session 4",
  "files": []
}
```

### Exemple
```bash
curl -X GET http://127.0.0.1:5000/api/affectations/presences_responsables/list/4
```

---

## 3️⃣ Télécharger un seul PDF

### Endpoint
```
GET /api/affectations/presences_responsables/download/<session_id>/<filename>
```

### Description
Télécharge un PDF spécifique de présence d'un responsable.

### Paramètres
- `session_id` (int, path): ID de la session
- `filename` (string, path): Nom du fichier PDF à télécharger

### Réponse Succès (200)
Retourne le fichier PDF en téléchargement direct.

### Réponse Erreur (404)
```json
{
  "success": false,
  "error": "Fichier non trouvé",
  "filepath": "results/presences_responsables/session_4/presence_responsable_UNKNOWN_4.pdf"
}
```

### Exemple
```bash
curl -X GET \
  http://127.0.0.1:5000/api/affectations/presences_responsables/download/4/presence_responsable_DUPONT_Jean_4.pdf \
  --output presence_DUPONT.pdf
```

---

## 4️⃣ Télécharger plusieurs PDFs en ZIP

### Endpoint
```
POST /api/affectations/presences_responsables/download-multiple/<session_id>
```

### Description
Télécharge plusieurs PDFs de présence en un seul fichier ZIP.
Peut télécharger une sélection spécifique ou tous les fichiers.

### Paramètres
- `session_id` (int, path): ID de la session

### Body JSON (Option 1: Sélection spécifique)
```json
{
  "filenames": [
    "presence_responsable_DUPONT_Jean_4.pdf",
    "presence_responsable_MARTIN_Marie_4.pdf",
    "presence_responsable_BERNARD_Paul_4.pdf"
  ],
  "download_all": false
}
```

### Body JSON (Option 2: Télécharger tout)
```json
{
  "download_all": true
}
```

### Réponse Succès (200)
Retourne un fichier ZIP en téléchargement direct.
Nom du fichier: `presences_responsables_session_<id>_<timestamp>.zip`

Exemple: `presences_responsables_session_4_20251018_143000.zip`

### Réponse Erreur (400)
```json
{
  "error": "Corps de requête JSON requis",
  "expected": {
    "filenames": ["file1.pdf", "file2.pdf"],
    "download_all": false
  }
}
```

### Réponse Erreur (404)
```json
{
  "error": "Aucun PDF de présence trouvé pour la session 4"
}
```

### Réponse Erreur (404 - Aucun fichier valide)
```json
{
  "error": "Aucun fichier valide trouvé",
  "missing_files": [
    "presence_responsable_UNKNOWN1_4.pdf",
    "presence_responsable_UNKNOWN2_4.pdf"
  ]
}
```

### Exemple 1: Télécharger une sélection
```bash
curl -X POST \
  http://127.0.0.1:5000/api/affectations/presences_responsables/download-multiple/4 \
  -H "Content-Type: application/json" \
  -d '{
    "filenames": [
      "presence_responsable_DUPONT_Jean_4.pdf",
      "presence_responsable_MARTIN_Marie_4.pdf"
    ],
    "download_all": false
  }' \
  --output presences_selection.zip
```

### Exemple 2: Télécharger tous
```bash
curl -X POST \
  http://127.0.0.1:5000/api/affectations/presences_responsables/download-multiple/4 \
  -H "Content-Type: application/json" \
  -d '{"download_all": true}' \
  --output presences_all.zip
```

---

## 🔄 Workflow Complet

### Scénario type d'utilisation

```javascript
// 1. Générer les PDFs
const generateResponse = await fetch(
  'http://127.0.0.1:5000/api/affectations/generate_presences_responsables/4'
);
// Response: { "message": "...", "nombre_responsables": 3 }

// 2. Lister les PDFs disponibles
const listResponse = await fetch(
  'http://127.0.0.1:5000/api/affectations/presences_responsables/list/4'
);
const { files } = await listResponse.json();
// Response: { "success": true, "count": 3, "files": [...] }

// 3. Télécharger une sélection en ZIP
const downloadResponse = await fetch(
  'http://127.0.0.1:5000/api/affectations/presences_responsables/download-multiple/4',
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filenames: [files[0].filename, files[1].filename],
      download_all: false
    })
  }
);
const blob = await downloadResponse.blob();
// Télécharge: presences_responsables_session_4_20251018_143000.zip
```

---

## 📊 Comparaison avec les Convocations

| Fonctionnalité | Convocations | Présences Responsables |
|----------------|--------------|------------------------|
| **Source** | Table `affectation` | Table `responsable_absent_jour_examen` |
| **Titre PDF** | "Liste d'affectation des surveillants" | "Liste des créneaux de présence des responsables" |
| **Message** | "...assurer la surveillance et (ou) la responsabilité..." | "...assurer la responsabilité des examens..." |
| **Données** | Tous les créneaux de surveillance affectés | Créneaux où l'enseignant est responsable (champ `enseignant` dans `creneau`) |
| **Endpoint génération** | `/generate_convocations/<id>` | `/generate_presences_responsables/<id>` |
| **Endpoint liste** | `/convocations/list/<id>` | `/presences_responsables/list/<id>` |
| **Endpoint download ZIP** | ❌ (non disponible) | ✅ `/presences_responsables/download-multiple/<id>` |
| **Dossier stockage** | `results/convocations/session_<id>/` | `results/presences_responsables/session_<id>/` |

---

## 🎯 Cas d'usage

### Cas 1: Gestionnaire veut générer et télécharger tous les PDFs

```bash
# Étape 1: Générer
curl -X GET http://127.0.0.1:5000/api/affectations/generate_presences_responsables/4

# Étape 2: Télécharger tous
curl -X POST \
  http://127.0.0.1:5000/api/affectations/presences_responsables/download-multiple/4 \
  -H "Content-Type: application/json" \
  -d '{"download_all": true}' \
  --output presences_all.zip
```

### Cas 2: Secrétaire veut télécharger les PDFs de 3 enseignants spécifiques

```bash
# Étape 1: Lister pour connaître les noms exacts
curl -X GET http://127.0.0.1:5000/api/affectations/presences_responsables/list/4

# Étape 2: Télécharger la sélection
curl -X POST \
  http://127.0.0.1:5000/api/affectations/presences_responsables/download-multiple/4 \
  -H "Content-Type: application/json" \
  -d '{
    "filenames": [
      "presence_responsable_DUPONT_Jean_4.pdf",
      "presence_responsable_MARTIN_Marie_4.pdf",
      "presence_responsable_BERNARD_Paul_4.pdf"
    ],
    "download_all": false
  }' \
  --output presences_3enseignants.zip
```

### Cas 3: Enseignant veut consulter son propre PDF

```bash
# Télécharger directement un seul PDF
curl -X GET \
  http://127.0.0.1:5000/api/affectations/presences_responsables/download/4/presence_responsable_DUPONT_Jean_4.pdf \
  --output ma_presence.pdf
```

---

## ⚠️ Notes importantes

1. **Génération obligatoire**: Les PDFs doivent être générés avant de pouvoir être listés ou téléchargés
2. **Fichiers manquants**: Si un fichier de la liste n'existe pas, il est ignoré (pas d'erreur bloquante)
3. **Format du ZIP**: Le nom du fichier ZIP contient la date et l'heure pour éviter les conflits
4. **Sécurité**: Les noms de fichiers sont nettoyés avec `os.path.basename()` pour éviter les attaques path traversal
5. **Stockage**: Les PDFs sont stockés dans `results/presences_responsables/session_<id>/`

---

## 🔗 Endpoints Connexes

- **Table source**: `GET /api/presence/session/<id>` - Voir les responsables absents
- **Statistiques**: `GET /api/statistics/session/<id>` - Voir les stats globales
- **Convocations**: `GET /api/affectations/generate_convocations/<id>` - Générer les convocations de surveillance

---

## 📝 Structure du PDF généré

```
┌────────────────────────────────────────────┐
│            [LOGO]         HEADER           │
│  GESTION DES EXAMENS ET DÉLIBÉRATIONS      │
│  Liste des créneaux de présence des resp.  │
├────────────────────────────────────────────┤
│                                            │
│            Notes à                         │
│        Mr/Mme [Prénom] [Nom]               │
│                                            │
│  Cher(e) collègue,                         │
│  Vous êtes prié(e) d'assurer la           │
│  responsabilité des examens selon le       │
│  calendrier ci-joint.                      │
│                                            │
│  ┌──────────┬─────────┬─────────┐         │
│  │   Date   │  Heure  │  Durée  │         │
│  ├──────────┼─────────┼─────────┤         │
│  │27/10/2025│  10:30  │  1.5 H  │         │
│  │28/10/2025│  08:30  │  1.5 H  │         │
│  │28/10/2025│  10:30  │  1.5 H  │         │
│  │29/10/2025│  08:30  │  1.5 H  │         │
│  │29/10/2025│  10:30  │  1.5 H  │         │
│  │30/10/2025│  10:30  │  1.5 H  │         │
│  └──────────┴─────────┴─────────┘         │
│                                            │
│  Merci de votre collaboration.             │
│                                            │
├────────────────────────────────────────────┤
│            [FOOTER IMAGE]                  │
└────────────────────────────────────────────┘
```

---

C'est tout ! Vous avez maintenant une API complète pour gérer les PDFs de présence des responsables. 🎉
