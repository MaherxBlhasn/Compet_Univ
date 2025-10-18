# Guide Frontend - Gestion du Stockage

## 📚 Vue d'ensemble

Ce guide explique comment implémenter l'interface frontend pour gérer le stockage des fichiers générés (PDFs et CSVs) incluant :
- Affectations PDF/CSV
- Convocations PDF/CSV
- **Présences Responsables PDF** ✨ (nouveau)

---

## 🎯 Fonctionnalités disponibles

### 1. Visualisation de l'utilisation du stockage
### 2. Suppression par type de fichier (PDF, CSV, Tout)
### 3. Suppression par session
### 4. Nettoyage des dossiers vides

---

## 📡 API Service Layer

### `storageService.js`

```javascript
// services/storageService.js

const API_BASE_URL = 'http://127.0.0.1:5000/api/storage';

/**
 * Récupérer les informations sur l'utilisation du stockage
 * @returns {Promise<Object>} Informations détaillées sur le stockage
 */
export const getStorageInfo = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Erreur lors de la récupération des infos de stockage:', error);
    throw error;
  }
};

/**
 * Supprimer tous les fichiers d'un certain type
 * @param {string} type - 'pdf', 'csv', ou 'all' (défaut: 'all')
 * @returns {Promise<Object>} Résultat de la suppression
 */
export const deleteAllFiles = async (type = 'all') => {
  try {
    const response = await fetch(`${API_BASE_URL}/delete-all?type=${type}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Erreur lors de la suppression globale:', error);
    throw error;
  }
};

/**
 * Supprimer les fichiers d'une session spécifique
 * @param {number} sessionId - ID de la session
 * @param {string} type - 'pdf', 'csv', ou 'all' (défaut: 'all')
 * @returns {Promise<Object>} Résultat de la suppression
 */
export const deleteSessionFiles = async (sessionId, type = 'all') => {
  try {
    const response = await fetch(`${API_BASE_URL}/delete/session/${sessionId}?type=${type}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`Erreur lors de la suppression de la session ${sessionId}:`, error);
    throw error;
  }
};

/**
 * Nettoyer tous les dossiers vides
 * @returns {Promise<Object>} Résultat du nettoyage
 */
export const cleanupEmptyFolders = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/cleanup/empty`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Erreur lors du nettoyage des dossiers vides:', error);
    throw error;
  }
};
```

---

## 🎨 Composant React Principal

### `StorageManager.jsx`

```jsx
// components/StorageManager.jsx

import React, { useState, useEffect } from 'react';
import {
  getStorageInfo,
  deleteAllFiles,
  deleteSessionFiles,
  cleanupEmptyFolders
} from '../services/storageService';
import './StorageManager.css';

const StorageManager = () => {
  const [storageData, setStorageData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSession, setSelectedSession] = useState(null);
  const [deleteType, setDeleteType] = useState('all');

  // Charger les données au montage
  useEffect(() => {
    loadStorageData();
  }, []);

  const loadStorageData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getStorageInfo();
      setStorageData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAll = async () => {
    const confirmMessage = `⚠️ ATTENTION : Vous allez supprimer TOUS les fichiers ${
      deleteType === 'pdf' ? 'PDF' : deleteType === 'csv' ? 'CSV' : 'PDF et CSV'
    }.\n\nCette action est IRRÉVERSIBLE!\n\nContinuer?`;

    if (!window.confirm(confirmMessage)) {
      return;
    }

    try {
      setLoading(true);
      const result = await deleteAllFiles(deleteType);
      alert(`✅ ${result.message}`);
      await loadStorageData(); // Recharger les données
    } catch (err) {
      alert(`❌ Erreur: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSession = async (sessionId) => {
    const confirmMessage = `Supprimer tous les fichiers ${
      deleteType === 'pdf' ? 'PDF' : deleteType === 'csv' ? 'CSV' : 'PDF et CSV'
    } de la session ${sessionId}?`;

    if (!window.confirm(confirmMessage)) {
      return;
    }

    try {
      setLoading(true);
      const result = await deleteSessionFiles(sessionId, deleteType);
      alert(`✅ ${result.message}`);
      await loadStorageData();
    } catch (err) {
      alert(`❌ ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCleanupEmpty = async () => {
    if (!window.confirm('Nettoyer tous les dossiers vides?')) {
      return;
    }

    try {
      setLoading(true);
      const result = await cleanupEmptyFolders();
      alert(`✅ ${result.message}`);
      await loadStorageData();
    } catch (err) {
      alert(`❌ Erreur: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !storageData) {
    return (
      <div className="storage-manager">
        <div className="loading">
          <div className="spinner"></div>
          <p>Chargement des données de stockage...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="storage-manager">
        <div className="error-container">
          <h3>❌ Erreur</h3>
          <p>{error}</p>
          <button onClick={loadStorageData} className="btn-retry">
            Réessayer
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="storage-manager">
      {/* Header */}
      <div className="storage-header">
        <h2>💾 Gestion du Stockage</h2>
        <button onClick={loadStorageData} className="btn-refresh" disabled={loading}>
          🔄 Actualiser
        </button>
      </div>

      {/* Vue d'ensemble */}
      <div className="storage-overview">
        <h3>📊 Vue d'ensemble</h3>
        <div className="overview-cards">
          <div className="storage-card total">
            <div className="card-icon">💽</div>
            <div className="card-content">
              <div className="card-label">Total général</div>
              <div className="card-value">{storageData.totals.total_all.formatted}</div>
              <div className="card-files">{storageData.total_files} fichiers</div>
            </div>
          </div>

          <div className="storage-card pdf">
            <div className="card-icon">📄</div>
            <div className="card-content">
              <div className="card-label">Total PDFs</div>
              <div className="card-value">{storageData.totals.total_pdf.formatted}</div>
              <div className="card-files">
                {(storageData.file_counts.affectations_pdf +
                  storageData.file_counts.convocations_pdf +
                  storageData.file_counts.presences_responsables_pdf)} fichiers
              </div>
            </div>
          </div>

          <div className="storage-card csv">
            <div className="card-icon">📊</div>
            <div className="card-content">
              <div className="card-label">Total CSVs</div>
              <div className="card-value">{storageData.totals.total_csv.formatted}</div>
              <div className="card-files">
                {(storageData.file_counts.affectations_csv +
                  storageData.file_counts.convocations_csv)} fichiers
              </div>
            </div>
          </div>

          <div className="storage-card sessions">
            <div className="card-icon">📅</div>
            <div className="card-content">
              <div className="card-label">Sessions</div>
              <div className="card-value">{storageData.total_sessions}</div>
              <div className="card-files">sessions actives</div>
            </div>
          </div>
        </div>
      </div>

      {/* Détail par catégorie */}
      <div className="storage-details">
        <h3>📁 Détail par catégorie</h3>
        <table className="storage-table">
          <thead>
            <tr>
              <th>Catégorie</th>
              <th>Taille</th>
              <th>Fichiers</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>📄 Affectations PDF</td>
              <td>{storageData.totals.affectations_pdf.formatted}</td>
              <td>{storageData.file_counts.affectations_pdf}</td>
            </tr>
            <tr>
              <td>📊 Affectations CSV</td>
              <td>{storageData.totals.affectations_csv.formatted}</td>
              <td>{storageData.file_counts.affectations_csv}</td>
            </tr>
            <tr>
              <td>📄 Convocations PDF</td>
              <td>{storageData.totals.convocations_pdf.formatted}</td>
              <td>{storageData.file_counts.convocations_pdf}</td>
            </tr>
            <tr>
              <td>📊 Convocations CSV</td>
              <td>{storageData.totals.convocations_csv.formatted}</td>
              <td>{storageData.file_counts.convocations_csv}</td>
            </tr>
            <tr className="highlight-row">
              <td>✨ Présences Responsables PDF</td>
              <td>{storageData.totals.presences_responsables_pdf.formatted}</td>
              <td>{storageData.file_counts.presences_responsables_pdf}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Actions de suppression globale */}
      <div className="storage-actions">
        <h3>🗑️ Actions de suppression</h3>
        
        <div className="action-section">
          <div className="action-controls">
            <label>Type de fichier :</label>
            <select value={deleteType} onChange={(e) => setDeleteType(e.target.value)}>
              <option value="all">Tous (PDF + CSV)</option>
              <option value="pdf">PDFs uniquement</option>
              <option value="csv">CSVs uniquement</option>
            </select>
          </div>

          <button
            onClick={handleDeleteAll}
            className="btn-delete-all"
            disabled={loading}
          >
            🗑️ Supprimer TOUS les fichiers ({deleteType})
          </button>

          <button
            onClick={handleCleanupEmpty}
            className="btn-cleanup"
            disabled={loading}
          >
            🧹 Nettoyer les dossiers vides
          </button>
        </div>
      </div>

      {/* Détail par session */}
      <div className="storage-sessions">
        <h3>📅 Stockage par session</h3>
        
        {storageData.sessions.length === 0 ? (
          <div className="empty-state">
            <p>Aucune session avec des fichiers générés</p>
          </div>
        ) : (
          <div className="sessions-list">
            {storageData.sessions.map((session) => (
              <div key={session.session_id} className="session-card">
                <div className="session-header">
                  <h4>Session {session.session_id}</h4>
                  <div className="session-total">{session.total.formatted}</div>
                </div>

                <div className="session-details">
                  <div className="session-row">
                    <span className="label">📄 Affectations PDF:</span>
                    <span className="value">
                      {session.affectations_pdf ? session.affectations_pdf.formatted : '-'}
                    </span>
                  </div>
                  <div className="session-row">
                    <span className="label">📊 Affectations CSV:</span>
                    <span className="value">
                      {session.affectations_csv ? session.affectations_csv.formatted : '-'}
                    </span>
                  </div>
                  <div className="session-row">
                    <span className="label">📄 Convocations PDF:</span>
                    <span className="value">
                      {session.convocations_pdf ? session.convocations_pdf.formatted : '-'}
                    </span>
                  </div>
                  <div className="session-row">
                    <span className="label">📊 Convocations CSV:</span>
                    <span className="value">
                      {session.convocations_csv ? session.convocations_csv.formatted : '-'}
                    </span>
                  </div>
                  <div className="session-row highlight">
                    <span className="label">✨ Présences Resp. PDF:</span>
                    <span className="value">
                      {session.presences_responsables_pdf ? session.presences_responsables_pdf.formatted : '-'}
                    </span>
                  </div>
                </div>

                <div className="session-actions">
                  <button
                    onClick={() => handleDeleteSession(session.session_id)}
                    className="btn-delete-session"
                    disabled={loading}
                  >
                    🗑️ Supprimer ({deleteType})
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default StorageManager;
```

---

## 🎨 Styles CSS

### `StorageManager.css`

```css
/* components/StorageManager.css */

.storage-manager {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
}

/* Header */
.storage-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 2px solid #e0e0e0;
}

.storage-header h2 {
  margin: 0;
  color: #333;
  font-size: 28px;
}

.btn-refresh {
  padding: 10px 20px;
  background-color: #4CAF50;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
}

.btn-refresh:hover:not(:disabled) {
  background-color: #45a049;
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Overview Cards */
.storage-overview {
  margin-bottom: 30px;
}

.storage-overview h3 {
  color: #333;
  margin-bottom: 15px;
}

.overview-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.storage-card {
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  gap: 15px;
  transition: transform 0.2s, box-shadow 0.2s;
}

.storage-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.storage-card.total {
  border-left: 4px solid #2196F3;
}

.storage-card.pdf {
  border-left: 4px solid #FF5722;
}

.storage-card.csv {
  border-left: 4px solid #4CAF50;
}

.storage-card.sessions {
  border-left: 4px solid #9C27B0;
}

.card-icon {
  font-size: 40px;
  opacity: 0.8;
}

.card-content {
  flex: 1;
}

.card-label {
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 5px;
}

.card-value {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  margin-bottom: 3px;
}

.card-files {
  font-size: 12px;
  color: #999;
}

/* Storage Details Table */
.storage-details {
  margin-bottom: 30px;
}

.storage-details h3 {
  color: #333;
  margin-bottom: 15px;
}

.storage-table {
  width: 100%;
  background: white;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.storage-table thead {
  background-color: #f5f5f5;
}

.storage-table th {
  padding: 15px;
  text-align: left;
  font-weight: 600;
  color: #555;
  border-bottom: 2px solid #e0e0e0;
}

.storage-table td {
  padding: 12px 15px;
  border-bottom: 1px solid #f0f0f0;
}

.storage-table tbody tr:hover {
  background-color: #f9f9f9;
}

.storage-table .highlight-row {
  background-color: #fff3e0;
  font-weight: 500;
}

.storage-table .highlight-row:hover {
  background-color: #ffe0b2;
}

/* Actions Section */
.storage-actions {
  margin-bottom: 30px;
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.storage-actions h3 {
  color: #333;
  margin-bottom: 15px;
}

.action-section {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.action-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.action-controls label {
  font-weight: 500;
  color: #555;
}

.action-controls select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 5px;
  font-size: 14px;
  cursor: pointer;
}

.btn-delete-all {
  padding: 12px 24px;
  background-color: #f44336;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 16px;
  font-weight: 500;
  transition: background-color 0.3s;
}

.btn-delete-all:hover:not(:disabled) {
  background-color: #d32f2f;
}

.btn-delete-all:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-cleanup {
  padding: 12px 24px;
  background-color: #FF9800;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 16px;
  font-weight: 500;
  transition: background-color 0.3s;
}

.btn-cleanup:hover:not(:disabled) {
  background-color: #F57C00;
}

.btn-cleanup:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Sessions Section */
.storage-sessions h3 {
  color: #333;
  margin-bottom: 15px;
}

.sessions-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.session-card {
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #2196F3;
  transition: transform 0.2s, box-shadow 0.2s;
}

.session-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 2px solid #e0e0e0;
}

.session-header h4 {
  margin: 0;
  color: #333;
  font-size: 18px;
}

.session-total {
  font-size: 20px;
  font-weight: bold;
  color: #2196F3;
}

.session-details {
  margin-bottom: 15px;
}

.session-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.session-row:last-child {
  border-bottom: none;
}

.session-row.highlight {
  background-color: #fff3e0;
  padding: 8px 10px;
  margin: 5px -10px;
  border-radius: 5px;
  font-weight: 500;
}

.session-row .label {
  color: #666;
  font-size: 14px;
}

.session-row .value {
  color: #333;
  font-weight: 500;
  font-size: 14px;
}

.session-actions {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 2px solid #e0e0e0;
}

.btn-delete-session {
  width: 100%;
  padding: 10px;
  background-color: #f44336;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.3s;
}

.btn-delete-session:hover:not(:disabled) {
  background-color: #d32f2f;
}

.btn-delete-session:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Loading & Error States */
.loading {
  text-align: center;
  padding: 60px 20px;
}

.spinner {
  border: 4px solid #f3f3f3;
  border-top: 4px solid #2196F3;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin: 0 auto 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-container {
  background: #ffebee;
  border: 1px solid #f44336;
  border-radius: 10px;
  padding: 30px;
  text-align: center;
  max-width: 500px;
  margin: 40px auto;
}

.error-container h3 {
  color: #c62828;
  margin-bottom: 15px;
}

.error-container p {
  color: #666;
  margin-bottom: 20px;
}

.btn-retry {
  padding: 10px 20px;
  background-color: #2196F3;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
}

.btn-retry:hover {
  background-color: #1976D2;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  background: #f5f5f5;
  border-radius: 10px;
  color: #999;
  font-style: italic;
}

/* Responsive */
@media (max-width: 768px) {
  .overview-cards {
    grid-template-columns: 1fr;
  }

  .sessions-list {
    grid-template-columns: 1fr;
  }

  .storage-header {
    flex-direction: column;
    gap: 15px;
    align-items: flex-start;
  }

  .action-controls {
    flex-direction: column;
    align-items: flex-start;
  }
}
```

---

## 🔗 Intégration dans votre application

### Étape 1: Importer le composant

```jsx
// App.js ou votre fichier de routing

import StorageManager from './components/StorageManager';

function App() {
  return (
    <div className="App">
      {/* ... autres routes ... */}
      
      <Route path="/storage" element={<StorageManager />} />
    </div>
  );
}
```

### Étape 2: Ajouter un lien dans votre menu de navigation

```jsx
// Navigation.jsx

<nav>
  <Link to="/sessions">Sessions</Link>
  <Link to="/affectations">Affectations</Link>
  <Link to="/convocations">Convocations</Link>
  <Link to="/storage">💾 Stockage</Link>  {/* Nouveau */}
</nav>
```

---

## 📊 Exemples de réponses API

### GET `/api/storage/`

```json
{
  "success": true,
  "totals": {
    "affectations_pdf": {"value": 2.5, "unit": "MB", "formatted": "2.50 MB"},
    "affectations_csv": {"value": 150, "unit": "KB", "formatted": "150.00 KB"},
    "convocations_pdf": {"value": 1.8, "unit": "MB", "formatted": "1.80 MB"},
    "convocations_csv": {"value": 120, "unit": "KB", "formatted": "120.00 KB"},
    "presences_responsables_pdf": {"value": 0.5, "unit": "MB", "formatted": "0.50 MB"},
    "total_pdf": {"value": 4.8, "unit": "MB", "formatted": "4.80 MB"},
    "total_csv": {"value": 270, "unit": "KB", "formatted": "270.00 KB"},
    "total_all": {"value": 5.06, "unit": "MB", "formatted": "5.06 MB"}
  },
  "file_counts": {
    "affectations_pdf": 25,
    "affectations_csv": 8,
    "convocations_pdf": 25,
    "convocations_csv": 8,
    "presences_responsables_pdf": 3
  },
  "total_files": 69,
  "sessions": [
    {
      "session_id": 4,
      "affectations_pdf": {"value": 2.5, "unit": "MB", "formatted": "2.50 MB"},
      "affectations_csv": {"value": 150, "unit": "KB", "formatted": "150.00 KB"},
      "convocations_pdf": {"value": 1.8, "unit": "MB", "formatted": "1.80 MB"},
      "convocations_csv": {"value": 120, "unit": "KB", "formatted": "120.00 KB"},
      "presences_responsables_pdf": {"value": 0.5, "unit": "MB", "formatted": "0.50 MB"},
      "total": {"value": 5.06, "unit": "MB", "formatted": "5.06 MB"}
    }
  ],
  "total_sessions": 1
}
```

---

## 🎯 Scénarios d'utilisation

### Scénario 1: Visualiser l'utilisation du stockage

1. L'utilisateur accède à la page `/storage`
2. Le composant charge automatiquement les données
3. Affichage des cartes récapitulatives :
   - Total général (5.06 MB, 69 fichiers)
   - Total PDFs (4.8 MB)
   - Total CSVs (270 KB)
   - Nombre de sessions (1)
4. Tableau détaillé par catégorie avec **Présences Responsables PDF** en surbrillance
5. Liste des sessions avec détail par type de fichier

### Scénario 2: Supprimer tous les PDFs

1. L'utilisateur sélectionne "PDFs uniquement" dans le menu déroulant
2. Clique sur "🗑️ Supprimer TOUS les fichiers (pdf)"
3. Confirmation demandée avec message d'avertissement
4. Après confirmation:
   - Tous les PDFs (affectations, convocations, présences) sont supprimés
   - Les CSVs restent intacts
   - Toast de confirmation : "✅ 53 fichiers supprimés"
   - Rechargement automatique des données

### Scénario 3: Supprimer les fichiers d'une session spécifique

1. L'utilisateur scroll vers la section "Stockage par session"
2. Sélectionne le type "Tous (PDF + CSV)"
3. Clique sur "🗑️ Supprimer (all)" pour la session 4
4. Confirmation demandée
5. Tous les fichiers de la session 4 sont supprimés
6. La carte de la session disparaît de la liste

### Scénario 4: Nettoyer les dossiers vides

1. Après plusieurs suppressions, des dossiers `session_*` vides peuvent rester
2. L'utilisateur clique sur "🧹 Nettoyer les dossiers vides"
3. Tous les dossiers `session_*` vides sont supprimés
4. Toast : "✅ 3 dossiers vides supprimés"

---

## 🧪 Tests avec cURL

### Test 1: Récupérer les infos de stockage
```bash
curl -X GET http://127.0.0.1:5000/api/storage/
```

### Test 2: Supprimer tous les PDFs
```bash
curl -X DELETE "http://127.0.0.1:5000/api/storage/delete-all?type=pdf"
```

### Test 3: Supprimer tous les CSVs
```bash
curl -X DELETE "http://127.0.0.1:5000/api/storage/delete-all?type=csv"
```

### Test 4: Supprimer tous les fichiers
```bash
curl -X DELETE "http://127.0.0.1:5000/api/storage/delete-all?type=all"
```

### Test 5: Supprimer les fichiers de la session 4 (PDFs uniquement)
```bash
curl -X DELETE "http://127.0.0.1:5000/api/storage/delete/session/4?type=pdf"
```

### Test 6: Nettoyer les dossiers vides
```bash
curl -X DELETE http://127.0.0.1:5000/api/storage/cleanup/empty
```

---

## ⚠️ Points d'attention

### Sécurité
- **Confirmation obligatoire** : Toutes les suppressions nécessitent une confirmation utilisateur
- **Messages clairs** : Les messages d'avertissement indiquent clairement ce qui sera supprimé
- **Action irréversible** : Bien informer l'utilisateur que les fichiers ne peuvent pas être récupérés

### Performance
- **Rechargement intelligent** : Les données sont rechargées uniquement après une action de suppression
- **Indicateurs de chargement** : Spinner affiché pendant les opérations longues
- **Gestion d'erreurs** : Les erreurs sont capturées et affichées de manière claire

### UX
- **Feedback visuel** : 
  - Boutons désactivés pendant le chargement
  - Animations sur les cartes au survol
  - Surbrillance pour la nouvelle catégorie "Présences Responsables"
- **Responsive** : Interface adaptée aux mobiles et tablettes
- **État vide** : Message affiché quand aucune session n'a de fichiers

---

## 🎨 Personnalisation

### Changer les couleurs

```css
/* Modifier les couleurs des cartes */
.storage-card.total {
  border-left: 4px solid #YOUR_COLOR;
}

/* Couleur pour les présences responsables */
.storage-table .highlight-row {
  background-color: #YOUR_HIGHLIGHT_COLOR;
}
```

### Ajouter des icônes personnalisées

```jsx
// Dans StorageManager.jsx
const CATEGORY_ICONS = {
  affectations_pdf: '📋',
  convocations_pdf: '📞',
  presences_responsables_pdf: '👔',  // Personnalisez ici
  affectations_csv: '📊',
  convocations_csv: '📈'
};
```

---

## 🚀 Prochaines étapes

1. **Tester l'API** avec les commandes cURL ci-dessus
2. **Créer le composant React** `StorageManager.jsx`
3. **Créer le service** `storageService.js`
4. **Ajouter les styles** `StorageManager.css`
5. **Intégrer** dans votre routing
6. **Tester** les différents scénarios

---

## 📝 Résumé

Vous avez maintenant :
- ✅ Une API complète pour gérer le stockage
- ✅ Un composant React complet avec toutes les fonctionnalités
- ✅ Un service layer pour communiquer avec l'API
- ✅ Des styles CSS professionnels et responsifs
- ✅ Support complet du nouveau dossier **presences_responsables** ✨
- ✅ Gestion des erreurs et états de chargement
- ✅ Confirmations de suppression pour éviter les accidents
- ✅ Interface intuitive et moderne

Le système de gestion du stockage est maintenant **complet et production-ready** ! 🎉
