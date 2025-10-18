# Guide Frontend - Génération et Téléchargement des PDFs de Présence Responsables

## 📚 Vue d'ensemble

Ce guide explique comment implémenter l'interface utilisateur pour générer et télécharger les PDFs de présence des enseignants responsables.

---

## 🎯 Workflow Complet

```
1. Utilisateur sélectionne une session
2. Clic sur "Générer les PDF de présence"
3. Backend génère les PDFs
4. Affichage de la liste des PDFs générés
5. Utilisateur sélectionne un ou plusieurs PDFs (ou tous)
6. Clic sur "Télécharger"
7. Téléchargement en ZIP
```

---

## 🔗 Endpoints API

### 1. Générer les PDFs
```
GET /api/affectations/generate_presences_responsables/<session_id>
```

### 2. Lister les PDFs disponibles
```
GET /api/affectations/presences_responsables/list/<session_id>
```

### 3. Télécharger un seul PDF
```
GET /api/affectations/presences_responsables/download/<session_id>/<filename>
```

### 4. Télécharger plusieurs PDFs en ZIP
```
POST /api/affectations/presences_responsables/download-multiple/<session_id>
Body: {
  "filenames": ["file1.pdf", "file2.pdf"],
  "download_all": false
}
```

---

## 💻 Implémentation Frontend

### Étape 1: Service API (JavaScript/TypeScript)

```javascript
// services/presencesResponsablesService.js

const BASE_URL = 'http://127.0.0.1:5000/api/affectations';

/**
 * Génère les PDFs de présence des responsables pour une session
 */
export async function generatePresencesResponsables(sessionId) {
  try {
    const response = await fetch(
      `${BASE_URL}/generate_presences_responsables/${sessionId}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || 'Erreur lors de la génération');
    }

    return await response.json();
  } catch (error) {
    console.error('Erreur generatePresencesResponsables:', error);
    throw error;
  }
}

/**
 * Liste les PDFs de présence disponibles pour une session
 */
export async function listPresencesResponsables(sessionId) {
  try {
    const response = await fetch(
      `${BASE_URL}/presences_responsables/list/${sessionId}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );

    if (!response.ok) {
      if (response.status === 404) {
        return { success: false, files: [], count: 0 };
      }
      throw new Error('Erreur lors de la récupération de la liste');
    }

    return await response.json();
  } catch (error) {
    console.error('Erreur listPresencesResponsables:', error);
    throw error;
  }
}

/**
 * Télécharge un seul PDF
 */
export async function downloadSinglePresence(sessionId, filename) {
  try {
    const url = `${BASE_URL}/presences_responsables/download/${sessionId}/${filename}`;
    
    // Ouvrir dans un nouvel onglet ou télécharger directement
    window.open(url, '_blank');
  } catch (error) {
    console.error('Erreur downloadSinglePresence:', error);
    throw error;
  }
}

/**
 * Télécharge plusieurs PDFs en ZIP
 */
export async function downloadMultiplePresences(sessionId, filenames, downloadAll = false) {
  try {
    const response = await fetch(
      `${BASE_URL}/presences_responsables/download-multiple/${sessionId}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filenames: filenames,
          download_all: downloadAll,
        }),
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Erreur lors du téléchargement');
    }

    // Créer un blob et télécharger
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    
    // Récupérer le nom du fichier depuis les headers
    const contentDisposition = response.headers.get('Content-Disposition');
    const filenameMatch = contentDisposition?.match(/filename="?(.+)"?/);
    const filename = filenameMatch 
      ? filenameMatch[1] 
      : `presences_responsables_session_${sessionId}.zip`;
    
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    return { success: true, filename };
  } catch (error) {
    console.error('Erreur downloadMultiplePresences:', error);
    throw error;
  }
}
```

---

### Étape 2: Composant React

```jsx
// components/PresencesResponsablesManager.jsx

import React, { useState, useEffect } from 'react';
import {
  generatePresencesResponsables,
  listPresencesResponsables,
  downloadSinglePresence,
  downloadMultiplePresences,
} from '../services/presencesResponsablesService';

const PresencesResponsablesManager = ({ sessionId }) => {
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [message, setMessage] = useState(null);

  // Charger la liste des PDFs au montage
  useEffect(() => {
    if (sessionId) {
      loadFilesList();
    }
  }, [sessionId]);

  // Charger la liste des fichiers
  const loadFilesList = async () => {
    setLoading(true);
    try {
      const result = await listPresencesResponsables(sessionId);
      setFiles(result.files || []);
    } catch (error) {
      console.error('Erreur chargement:', error);
      setMessage({ type: 'error', text: 'Erreur lors du chargement de la liste' });
    } finally {
      setLoading(false);
    }
  };

  // Générer les PDFs
  const handleGenerate = async () => {
    setGenerating(true);
    setMessage(null);
    try {
      const result = await generatePresencesResponsables(sessionId);
      setMessage({ 
        type: 'success', 
        text: `${result.nombre_responsables} PDFs générés avec succès!` 
      });
      // Recharger la liste
      await loadFilesList();
    } catch (error) {
      setMessage({ 
        type: 'error', 
        text: error.message || 'Erreur lors de la génération' 
      });
    } finally {
      setGenerating(false);
    }
  };

  // Sélectionner/désélectionner un fichier
  const toggleFileSelection = (filename) => {
    setSelectedFiles(prev => 
      prev.includes(filename)
        ? prev.filter(f => f !== filename)
        : [...prev, filename]
    );
  };

  // Sélectionner tous
  const selectAll = () => {
    setSelectedFiles(files.map(f => f.filename));
  };

  // Désélectionner tous
  const deselectAll = () => {
    setSelectedFiles([]);
  };

  // Télécharger un seul fichier
  const handleDownloadSingle = (filename) => {
    try {
      downloadSinglePresence(sessionId, filename);
      setMessage({ type: 'success', text: `Téléchargement de ${filename}` });
    } catch (error) {
      setMessage({ type: 'error', text: 'Erreur lors du téléchargement' });
    }
  };

  // Télécharger les fichiers sélectionnés
  const handleDownloadSelected = async () => {
    if (selectedFiles.length === 0) {
      setMessage({ type: 'warning', text: 'Aucun fichier sélectionné' });
      return;
    }

    setLoading(true);
    try {
      const result = await downloadMultiplePresences(sessionId, selectedFiles, false);
      setMessage({ 
        type: 'success', 
        text: `${selectedFiles.length} fichier(s) téléchargé(s) en ZIP` 
      });
    } catch (error) {
      setMessage({ type: 'error', text: 'Erreur lors du téléchargement' });
    } finally {
      setLoading(false);
    }
  };

  // Télécharger tous les fichiers
  const handleDownloadAll = async () => {
    if (files.length === 0) {
      setMessage({ type: 'warning', text: 'Aucun fichier disponible' });
      return;
    }

    setLoading(true);
    try {
      const result = await downloadMultiplePresences(sessionId, [], true);
      setMessage({ 
        type: 'success', 
        text: `Tous les fichiers (${files.length}) téléchargés en ZIP` 
      });
    } catch (error) {
      setMessage({ type: 'error', text: 'Erreur lors du téléchargement' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="presences-responsables-manager">
      <h2>📄 PDFs de Présence des Responsables</h2>
      
      {/* Message */}
      {message && (
        <div className={`alert alert-${message.type}`}>
          {message.text}
        </div>
      )}

      {/* Bouton de génération */}
      <div className="actions-top">
        <button
          onClick={handleGenerate}
          disabled={generating || loading}
          className="btn btn-primary"
        >
          {generating ? '⏳ Génération en cours...' : '🔄 Générer les PDFs'}
        </button>
        
        <button
          onClick={loadFilesList}
          disabled={loading}
          className="btn btn-secondary"
        >
          🔃 Actualiser la liste
        </button>
      </div>

      {/* Liste des fichiers */}
      {loading ? (
        <div className="loading">Chargement...</div>
      ) : files.length === 0 ? (
        <div className="empty-state">
          <p>Aucun PDF généré pour cette session.</p>
          <p>Cliquez sur "Générer les PDFs" pour commencer.</p>
        </div>
      ) : (
        <>
          {/* Actions de sélection */}
          <div className="selection-actions">
            <button onClick={selectAll} className="btn btn-sm">
              ✅ Tout sélectionner
            </button>
            <button onClick={deselectAll} className="btn btn-sm">
              ❌ Tout désélectionner
            </button>
            <span className="selection-count">
              {selectedFiles.length} / {files.length} sélectionné(s)
            </span>
          </div>

          {/* Boutons de téléchargement */}
          <div className="download-actions">
            <button
              onClick={handleDownloadSelected}
              disabled={selectedFiles.length === 0 || loading}
              className="btn btn-success"
            >
              📦 Télécharger la sélection ({selectedFiles.length}) en ZIP
            </button>
            
            <button
              onClick={handleDownloadAll}
              disabled={loading}
              className="btn btn-info"
            >
              📦 Télécharger tous ({files.length}) en ZIP
            </button>
          </div>

          {/* Tableau des fichiers */}
          <table className="files-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={selectedFiles.length === files.length}
                    onChange={() => 
                      selectedFiles.length === files.length 
                        ? deselectAll() 
                        : selectAll()
                    }
                  />
                </th>
                <th>Nom du fichier</th>
                <th>Taille</th>
                <th>Date de création</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {files.map((file) => (
                <tr key={file.filename}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedFiles.includes(file.filename)}
                      onChange={() => toggleFileSelection(file.filename)}
                    />
                  </td>
                  <td>{file.filename}</td>
                  <td>{file.size_mb} MB</td>
                  <td>{file.created}</td>
                  <td>
                    <button
                      onClick={() => handleDownloadSingle(file.filename)}
                      className="btn btn-sm btn-primary"
                    >
                      📥 Télécharger
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
};

export default PresencesResponsablesManager;
```

---

### Étape 3: CSS

```css
/* styles/PresencesResponsablesManager.css */

.presences-responsables-manager {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.presences-responsables-manager h2 {
  margin-bottom: 20px;
  color: #003366;
}

/* Alerts */
.alert {
  padding: 12px 20px;
  border-radius: 4px;
  margin-bottom: 20px;
}

.alert-success {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.alert-error {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.alert-warning {
  background-color: #fff3cd;
  color: #856404;
  border: 1px solid #ffeaa7;
}

/* Actions */
.actions-top,
.selection-actions,
.download-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.selection-count {
  display: flex;
  align-items: center;
  font-weight: 500;
  color: #666;
}

/* Buttons */
.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background-color: #007bff;
  color: white;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-success {
  background-color: #28a745;
  color: white;
}

.btn-info {
  background-color: #17a2b8;
  color: white;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
}

/* Table */
.files-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  overflow: hidden;
}

.files-table thead {
  background-color: #f8f9fa;
}

.files-table th,
.files-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #dee2e6;
}

.files-table th {
  font-weight: 600;
  color: #495057;
}

.files-table tbody tr:hover {
  background-color: #f8f9fa;
}

.files-table tbody tr:last-child td {
  border-bottom: none;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  margin-top: 20px;
}

.empty-state p {
  margin: 10px 0;
  color: #6c757d;
}

/* Loading */
.loading {
  text-align: center;
  padding: 40px;
  font-size: 18px;
  color: #6c757d;
}
```

---

## 🎬 Scénarios d'utilisation

### Scénario 1: Télécharger tous les PDFs

```javascript
// L'utilisateur clique sur "Télécharger tous"
await downloadMultiplePresences(sessionId, [], true);
// → Télécharge un ZIP avec tous les PDFs
```

### Scénario 2: Télécharger une sélection

```javascript
// L'utilisateur sélectionne 3 fichiers
const selected = [
  "presence_responsable_DUPONT_Jean_4.pdf",
  "presence_responsable_MARTIN_Marie_4.pdf",
  "presence_responsable_BERNARD_Paul_4.pdf"
];

await downloadMultiplePresences(sessionId, selected, false);
// → Télécharge un ZIP avec les 3 PDFs sélectionnés
```

### Scénario 3: Télécharger un seul PDF

```javascript
// L'utilisateur clique sur le bouton télécharger d'une ligne
downloadSinglePresence(sessionId, "presence_responsable_DUPONT_Jean_4.pdf");
// → Ouvre le PDF dans un nouvel onglet ou télécharge directement
```

---

## 📋 Exemple d'intégration dans une page

```jsx
// pages/SessionDetails.jsx

import React from 'react';
import { useParams } from 'react-router-dom';
import PresencesResponsablesManager from '../components/PresencesResponsablesManager';

const SessionDetails = () => {
  const { sessionId } = useParams();

  return (
    <div className="session-details-page">
      <h1>Session {sessionId}</h1>
      
      {/* Autres sections: affectations, statistiques, etc. */}
      
      <section className="presences-section">
        <PresencesResponsablesManager sessionId={sessionId} />
      </section>
    </div>
  );
};

export default SessionDetails;
```

---

## 🧪 Tests

### Test avec cURL

```bash
# 1. Générer les PDFs
curl -X GET http://127.0.0.1:5000/api/affectations/generate_presences_responsables/4

# 2. Lister les PDFs
curl -X GET http://127.0.0.1:5000/api/affectations/presences_responsables/list/4

# 3. Télécharger plusieurs en ZIP
curl -X POST http://127.0.0.1:5000/api/affectations/presences_responsables/download-multiple/4 \
  -H "Content-Type: application/json" \
  -d '{
    "filenames": ["presence_responsable_NOM1_Prenom1_4.pdf", "presence_responsable_NOM2_Prenom2_4.pdf"],
    "download_all": false
  }' \
  --output presences.zip

# 4. Télécharger tous en ZIP
curl -X POST http://127.0.0.1:5000/api/affectations/presences_responsables/download-multiple/4 \
  -H "Content-Type: application/json" \
  -d '{"download_all": true}' \
  --output presences_all.zip
```

---

## 🔄 Workflow complet (Résumé visuel)

```
┌─────────────────────────────────────────────────────────────┐
│                    INTERFACE UTILISATEUR                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  ÉTAPE 1: Génération                                        │
│  Bouton: "Générer les PDFs"                                 │
│  GET /generate_presences_responsables/4                     │
│  → Backend crée les PDFs dans results/presences_responsables│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  ÉTAPE 2: Listage                                           │
│  GET /presences_responsables/list/4                         │
│  → Retourne liste des PDFs disponibles                      │
│  → Affichage dans un tableau avec checkboxes                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  ÉTAPE 3: Sélection                                         │
│  - Checkbox pour chaque fichier                             │
│  - Bouton "Tout sélectionner"                               │
│  - Bouton "Tout désélectionner"                             │
│  - Compteur: X / Y sélectionné(s)                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  ÉTAPE 4: Téléchargement                                    │
│  Option A: Télécharger la sélection                         │
│    POST /download-multiple/4                                │
│    Body: { "filenames": [...], "download_all": false }      │
│                                                              │
│  Option B: Télécharger tout                                 │
│    POST /download-multiple/4                                │
│    Body: { "download_all": true }                           │
│                                                              │
│  → Backend crée un ZIP et l'envoie au client                │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚠️ Points importants

1. **Génération avant téléchargement**: Les PDFs doivent être générés avant d'être téléchargés
2. **Sélection multiple**: L'utilisateur peut sélectionner un, plusieurs ou tous les fichiers
3. **Format ZIP**: Le téléchargement multiple se fait toujours en ZIP
4. **Nom du ZIP**: Contient la date et l'heure pour éviter les conflits
5. **Fichiers manquants**: Si un fichier sélectionné n'existe pas, il est ignoré (pas d'erreur bloquante)

---

## 🚀 Prochaines améliorations possibles

- Ajouter une prévisualisation PDF avant téléchargement
- Permettre la suppression de PDFs individuels
- Ajouter des filtres (par nom, date, etc.)
- Pagination si beaucoup de fichiers
- Recherche dans la liste
- Tri par colonne (nom, taille, date)

---

Avec ce guide, vous avez tout ce qu'il faut pour implémenter une interface complète de gestion des PDFs de présence des responsables ! 🎉
