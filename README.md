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
app/
  menu.py          Schéma du menu + chargement
  order.py         Commande structurée + validation contre le menu
  messages.py      Textes par langue, questions de clarification, récapitulatif, prix
  llm.py           Extraction structurée avec Claude (Haiku 5.5, Sonnet 5.5 en renfort)
  conversation.py  Déroulé d'un appel : commande -> allergies -> relecture -> confirmation
  cli.py           Démo en terminal
data/
  menu.json        Menu (identifiants stables, traductions par langue)
prompts/
  fr/              Textes destinés aux appelants (un dossier par langue)
  llm/             Instructions données à Claude
tests/             Tests unitaires (pytest, Claude simulé)
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

## Démo en terminal

Simule un appel au clavier. Nécessite `ANTHROPIC_API_KEY` dans `.env`.

```bash
.venv/bin/python -m app.cli
```

Exemple : « deux burgers bacon large dont un sans oignons et un coca », puis répondre aux questions.
À la fin, le ticket cuisine (lignes, total en centimes, note allergies) s'affiche en JSON.

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
