# Vérifications du projet indépendant

Vérifié de nouveau le 27 septembre 2026 sous Windows / Python 3.12 :

- **32 tests pytest réussis**, sans réseau : filtres, déduplication, reprises, limite d'évaluations, validation LLM, contrats HTTP simulés, notification en attente et restauration d'artefact.
- `python -m aggregator --demo` : deux offres fictives, une filtrée, une retenue, aucune erreur, aucun import et aucun courriel.
- Collecte HTTP réelle Remotive : 19 offres valides, aucune ligne invalide. Aucune offre ne correspondait aux filtres par défaut lors du contrôle.
- Intégration réelle avec stage-tracker dans un processus Uvicorn local séparé : import par HTTP, statut `a_considerer`, date d'envoi nulle et aucun doublon au deuxième passage.
- Fichiers Python et YAML vérifiés ; aucun import Python du premier projet.

Le premier projet mis à jour passe séparément **47 tests**, et `alembic check` ne détecte aucune différence de schéma.

Non exécutés : appels Anthropic facturés, envoi SMTP réel, workflow GitHub Actions sur un compte distant, déploiement cloud et tests PostgreSQL. Ces capacités nécessitent tes accès et leur configuration. Aucun secret n'est inclus. Le collecteur UdeM authentifié et les notifications Discord/Slack ne font pas partie de cette version.
