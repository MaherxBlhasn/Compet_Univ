import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import random

# Exemple de variables (enseignants, créneaux, quotas)
n_enseignants = 5
n_creneaux = 6
n_quota = 4

# Générer des blocs valides (solutions faisables)
blocks = []
for i in range(n_enseignants):
    for j in range(n_creneaux):
        quota = random.randint(1, n_quota)
        # Simuler la faisabilité (ex: contrainte hard)
        if (i + j + quota) % 3 == 0:
            blocks.append((i, j, quota))

# Sélectionner un bloc optimal (ex: le plus haut quota)
optimal_block = max(blocks, key=lambda x: x[2]) if blocks else None

fig = plt.figure(figsize=(8, 6))
ax = fig.add_subplot(111, projection='3d')

# Afficher les blocs faisables
for b in blocks:
    color = plt.cm.tab20((b[0]*n_creneaux + b[1]) % 20)
    ax.bar3d(b[0], b[1], 0, 0.8, 0.8, b[2], color=color, alpha=0.6)

# Mettre en évidence le bloc optimal
if optimal_block:
    ax.bar3d(optimal_block[0], optimal_block[1], 0, 0.8, 0.8, optimal_block[2], color='lime', alpha=1.0, edgecolor='black')
    ax.text(optimal_block[0], optimal_block[1], optimal_block[2]+0.5, 'OPTIMAL', color='black', fontsize=12)

ax.set_xlabel('Enseignant')
ax.set_ylabel('Créneau')
ax.set_zlabel('Quota')
ax.set_title('Visualisation 3D des solutions CP-SAT\n(blocs faisables et solution optimale)')
plt.tight_layout()
plt.show()
