# rbxcheck

Vérifie tes modèles 3D **avant** de les importer dans Roblox Studio.

`rbxcheck` lit les fichiers OBJ, STL, glTF/GLB et FBX (binaire). Il signale les problèmes
qui font échouer un import ou donnent un mauvais rendu : trop de triangles, plusieurs
matériaux sur un même mesh, UV manquantes, textures énormes, mauvaise échelle, noms par défaut de Blender...

- Python 3.12+ pur, **aucune dépendance**
- Utilisable dans un terminal, des scripts ou une CI (codes de sortie + sortie JSON)
- Lecture seule : ne modifie jamais tes fichiers

[English](README.md) | Français

## Installation

Avec [uv](https://docs.astral.sh/uv/) :

```bash
git clone <ce dépôt>
cd rbxcheck
uv tool install .      # installe la commande `rbxcheck`
```

Ou sans installer : `uv run rbxcheck modele.fbx`.

## Utilisation

```bash
rbxcheck caisse.fbx                # un fichier
rbxcheck assets/                   # tous les modèles d'un dossier (récursif)
rbxcheck -p accessory chapeau.glb  # budget plus strict pour les accessoires UGC
rbxcheck --strict *.obj            # les avertissements comptent comme des échecs
rbxcheck --json caisse.fbx         # sortie lisible par un programme
```

Les messages de l'outil sont en anglais. Le tableau des vérifications est dans le [README anglais](README.md#what-is-checked).

Codes de sortie : `0` tout va bien, `1` au moins un fichier échoue, `2` erreur d'utilisation.

## Bon à savoir

- **Les limites évoluent.** Les chiffres de Roblox ne sont pas identiques partout (environ 20 000 à
  21 000 triangles par mesh, 10 000 pour certains imports, 4 000 pour les accessoires rigides).
  Ce sont des valeurs par défaut : utilise `--max-triangles` et `--warn-triangles` pour suivre ce que Roblox annonce.
- Les tailles sont dans l'unité du fichier, avant toute transformation. Vérifie l'échelle de ton export.
- Les FBX ASCII ne sont pas gérés : exporte en FBX binaire (réglage par défaut de Blender).

## Développement

```bash
uv run pytest
```

## Licence

MIT
