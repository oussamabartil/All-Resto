# Allô Resto

L'assistant vocal qui prend les commandes téléphoniques de votre restaurant, les vérifie avec le menu
et les envoie en cuisine.

Français d'abord, multilingue ensuite. L'agent comprend la commande, la confronte au menu, pose les
questions de clarification et relit la commande avant de l'envoyer.

## Pile technique

| Rôle | Outil |
|---|---|
| Téléphonie / agent vocal | LiveKit Agents |
| Reconnaissance vocale | Deepgram Nova-3 (fr) |
| Synthèse vocale | Cartesia Sonic |
| Modèle de langage | Claude Haiku 5.5 (Sonnet 5.5 pour les cas complexes) |
| Backend | FastAPI |
| Base de données | PostgreSQL |
| Tableau de bord | React (plus tard) |

## Structure

```
app/            Code Python
  menu.py       Schéma du menu + chargement
  order.py      Schéma d'une commande structurée + validation contre le menu
data/
  menu.json     Menu (identifiants stables, traductions par langue)
prompts/fr/     Textes destinés aux appelants (un dossier par langue)
tests/          Tests unitaires (pytest)
```

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis remplir les clés
```

Pour la v0 (validation du menu uniquement), seuls `pydantic`, `python-dotenv` et `pytest` sont nécessaires :

```bash
pip install pydantic python-dotenv pytest
```

## Tests

```bash
.venv/bin/pytest -q
```

## Principes

1. Le modèle de langage ne produit jamais de texte libre pour la commande : il renvoie des données
   structurées qui référencent les identifiants du menu, par exemple
   `{"item": "burger_bacon", "size": "large", "modifiers": ["sans_oignons"]}`.
2. Les textes (salutations, confirmations, divulgation IA) sont dans `prompts/<langue>/`, jamais dans le code.
3. Le menu est stocké une seule fois, avec un identifiant stable par article et les traductions par langue.
4. Une allergie déclenche toujours une étape de confirmation et une note pour le personnel.
5. Code simple et lisible, pas d'abstraction inutile.
