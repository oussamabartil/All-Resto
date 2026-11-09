# Règles du projet

## Git
- Ne jamais exécuter `git push`, ajouter un remote, ou créer un dépôt distant.
- Créer des commits locaux après chaque étape terminée et testée.
- À la fin de chaque étape majeure, rappeler à l'utilisateur de faire `git push` lui-même.
- Indiquer le nombre de commits créés depuis le dernier push quand c'est pertinent.

## Code
- Python 3.11+, style simple et lisible.
- Les textes destinés aux appelants sont dans `prompts/<langue>/`, jamais dans le code.
- Le LLM ne produit jamais de texte libre pour la commande : uniquement des données structurées référençant les identifiants du menu (`data/menu.json`).
- Une allergie déclarée déclenche toujours une confirmation et une note pour le personnel.
- Ne jamais ajouter de ligne `Co-Authored-By` (ni aucune autre attribution) dans les messages de commit.
