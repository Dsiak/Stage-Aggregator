# Stage Aggregator

Deuxième projet indépendant : **surveiller → filtrer → évaluer → enregistrer → notifier**. Ce dépôt ne contient pas stage-tracker, ne l'importe jamais et ne lit pas sa base. La communication passe exclusivement par HTTP avec `X-API-Key`. Il doit être publié dans un dépôt GitHub distinct.

## Démarrage immédiat sans compte

Python 3.11+ (3.12 recommandé), terminal dans ce dossier :

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m aggregator --demo
.\.venv\Scripts\python.exe -m pytest -q
```

`--demo` utilise deux offres fictives, sans réseau, sans IA payante, sans import ni envoi de courriel. Son état est en mémoire. Le rapport est dans `reports/latest.json` ; le terminal n'affiche que les compteurs. Sous macOS/Linux, utiliser `python3` et `.venv/bin/python`.

## Source de départ : Remotive

Une requête à l'API publique Remotive récupère les offres de la catégorie `software-dev`. BeautifulSoup transforme les descriptions HTML en texte. Les champs conservés sont le titre, l'entreprise, la localisation telle que donnée par la source, la date de publication, le lien et la description. Les lignes malformées sont comptées et ignorées ; si toutes sont invalides, l'exécution échoue.

Le portail du stagiaire UdeM affiche les offres après connexion et contient des renseignements liés au dossier étudiant ; aucun collecteur authentifié UdeM ni identifiant universitaire n'est livré ou stocké. L'EBSI propose un RSS public, mais celui-ci concerne surtout les sciences de l'information et ne constitue pas le portail général des stages. Remotive fournit un contrat public documenté. Les offres Remotive sont surtout des emplois à distance : il est normal qu'un filtre strict sur les stages retourne **zéro résultat**. La source ne remplace pas une recherche exhaustive sur les portails universitaires.

Les liens et le nom Remotive restent présents dans les imports et courriels. Son API conseille au maximum quatre collectes quotidiennes et annonce un décalage de 24 heures. Ne pas utiliser cet outil pour republier les offres sur un autre job board. [Documentation et conditions Remotive](https://github.com/remotive-com/remote-jobs-api). [Portail UdeM](https://alerteemploi.umontreal.ca/home.htm).

## Paramétrer les critères

Modifier `config.toml`, ou copier vers `config.local.toml` et utiliser `--config config.local.toml` :

- `include_keywords` : au moins un mot-clé dans le titre ou la description.
- `require_internship` : exige une mention explicite de stage/internship/co-op.
- `locations` : au moins une correspondance dans la localisation de la source. Une localisation inconnue ne passe pas. `worldwide` reste à vérifier dans les conditions de l'offre.
- `exclude_unpaid` : exclut les offres explicitement non rémunérées ; une rémunération absente n'est pas une preuve qu'elles sont payées.
- `max_age_days` : ancienneté maximale, les dates futures sont exclues.
- `min_score` : seuil 0–100.
- `max_evaluations` : maximum de tentatives d'évaluation par exécution, y compris les erreurs. Les autres offres attendent le prochain passage.
- `notify_every_days` : 1 quotidien, 7 hebdomadaire.

Le profil fourni est **un exemple**, à remplacer par tes compétences et contraintes. Les chemins de configuration sont relatifs au fichier TOML. Ne pas inclure de coordonnées, mots de passe ou autres secrets dans le profil. `profile.local.txt` est ignoré par Git.

## Évaluation : règles ou Anthropic

Le mode par défaut `evaluator = "rules"` est un score déterministe par compétences communes ; il est explicitement marqué **sans IA** dans les résultats.

Pour le véritable LLM, choisir `evaluator = "anthropic"`, puis définir `ANTHROPIC_API_KEY` et `ANTHROPIC_MODEL` dans l'environnement. Choisir un modèle disponible sur ton compte qui prend en charge les outils. Le client utilise l'API Messages, un outil JSON contraint et une validation Pydantic du score et de la phrase. Un résultat invalide n'est jamais accepté silencieusement.

Le profil (limité à 6 000 caractères) et la description (16 000 caractères) sont alors transmis à Anthropic. Le modèle n'a accès à aucun outil d'écriture, secret de stage-tracker ou fonction d'envoi. Les descriptions sont traitées comme données non fiables. Les frais dépendent de ton compte et du modèle. Aucun appel Anthropic réel n'a été effectué pour les tests livrés. [API Messages officielle](https://platform.claude.com/docs/en/api/messages/create).

Le fichier `.env.example` est un aide-mémoire ; les variables doivent être définies dans le terminal ou dans les secrets GitHub. Il n'est pas chargé automatiquement.

## Intégration avec le premier dépôt

Installer **stage-tracker 2.1**, fourni séparément, puis appliquer `python -m alembic upgrade head` dans son environnement. La migration 0003 ajoute `a_considerer`, une date d'envoi nullable et des identifiants externes uniques. Faire une sauvegarde avant la migration d'une base existante.

Dans le terminal de l'agrégateur, configurer `STAGE_TRACKER_URL` (ex. `http://127.0.0.1:8000`) et `STAGE_TRACKER_API_KEY` (la clé du premier projet), puis :

```powershell
.\.venv\Scripts\python.exe -m aggregator --sync
```

Sans `--sync`, la collecte et le classement restent locaux. Avant tout appel LLM en mode synchronisé, l'agrégateur vérifie la version du contrat HTTP et l'authentification. Il recherche une entreprise existante, puis appelle au besoin `POST /companies`, et enfin `POST /applications` avec `status=a_considerer`, `sent_on=null`, le lien et la provenance.

**Aucune candidature n'est envoyée au recruteur.** Une offre retenue reste à examiner dans stage-tracker. Après ta candidature réelle, passer son statut à `envoyee` et corriger la date d'envoi si nécessaire. Les offres à considérer sont exclues du taux de réponse.

HTTPS est exigé hors localhost. Les clients HTTP de la source, d'Anthropic et de stage-tracker ne partagent pas les en-têtes d'authentification. Les redirections ne sont pas suivies.

## Déduplication et reprise

L'agrégateur possède son propre SQLite `state/aggregator.db`. Empreinte : titre + entreprise + localisation normalisés et hachés en SHA-256. C'est volontairement conservateur : une republication identique au même lieu reste dédupliquée. Des descriptions différentes avec le même triplet seront fusionnées ; une variation de titre ou de localisation peut rester un doublon.

Les statuts locaux sont `new`, `filtered`, `rejected`, `selected`, `imported`. Les évaluations validées sont mises en cache. Une erreur d'API conserve l'offre pour reprise au prochain passage ; les offres déjà importées ne sont pas recréées. Un identifiant externe unique est aussi enregistré dans stage-tracker : si la réponse HTTP ou l'état local est perdu, une recherche retrouve l'import. Les créations concurrentes portant le même identifiant sont protégées par une contrainte SQL.

Une offre importée puis supprimée volontairement de stage-tracker ne sera pas automatiquement recréée tant que son état local est conservé. Les scores et exclusions ne sont pas recalculés lorsque le profil change : pour une nouvelle campagne, utiliser un nouveau `state_path`. La vérification HTTP conserve la déduplication des anciens imports.

Un verrou de fichier empêche deux exécutions locales simultanées. Les erreurs enregistrent leur type, pas les réponses contenant potentiellement des secrets. Les reconnexions sont faites au passage suivant, sans boucle agressive de retries.

## Courriel quotidien ou hebdomadaire

Configurer `SMTP_HOST`, `SMTP_PORT`, `SMTP_TLS=ssl` (465) ou `starttls` (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM` et `MAIL_TO`, puis :

```powershell
.\.venv\Scripts\python.exe -m aggregator --sync --notify
```

Seules les offres importées non notifiées apparaissent dans le résumé, triées par score avec justification et lien source. Sans `--notify`, aucun email n'est envoyé. L'envoi est mémorisé seulement après acceptation par le serveur SMTP. Un arrêt brutal après acceptation mais avant sauvegarde peut entraîner un résumé en double ; une acceptation SMTP ne garantit pas la remise en boîte de réception. Les tests n'envoient aucun message réel. Discord/Slack ne sont pas intégrés à cette première version.

## GitHub Actions et persistance

Publier **ce dossier uniquement** dans un deuxième dépôt. `stage-tracker` reste dans le premier dépôt. Les tests de `.github/workflows/ci.yml` n'ont besoin d'aucune clé ni du premier dépôt.

La collecte planifiée utilise `0 8 * * *`, donc **08:00 UTC**, pas 08:00 heure locale. GitHub peut retarder ou suspendre certains lancements planifiés ; ce n'est pas un ordonnanceur temps réel. [Documentation GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Pour l'activer :

1. Déployer stage-tracker : un runner GitHub ne peut pas joindre le localhost de ton ordinateur.
2. Dans le deuxième dépôt, ajouter la variable `STAGE_TRACKER_URL` et le secret `STAGE_TRACKER_API_KEY`.
3. Pour Anthropic, ajouter le secret `ANTHROPIC_API_KEY`, la variable `ANTHROPIC_MODEL` et modifier `evaluator` dans le fichier de configuration versionné.
4. Pour le courriel, ajouter les secrets SMTP et `MAIL_FROM`/`MAIL_TO`, puis la variable `NOTIFICATIONS_ENABLED=true` quand tu veux les envois automatiques.
5. Définir la variable `AGGREGATOR_ENABLED=true`.
6. Lancer manuellement **Collecte quotidienne** avec `initialize_state=true` pour le tout premier démarrage. Les exécutions suivantes restaurent l'état précédent.

Le workflow sérialise les collectes et sauvegarde l'état même après une erreur partielle. Il utilise des artefacts conservés 90 jours, pas un cache présenté comme une base durable. Si aucun état n'est retrouvé, le cron échoue plutôt que repartir silencieusement de zéro. Le script de restauration n'extrait que le fichier SQLite attendu. Il ne télécharge aucun code exécutable depuis l'artefact.

Les artefacts sont accessibles aux personnes ayant accès en lecture au dépôt : ils contiennent les offres et leurs justifications, jamais les clés. Pour un profil personnel et des résultats confidentiels, utiliser un dépôt privé. Sauvegarder l'état ailleurs pour une conservation durable. Après perte complète de l'état, les imports se réconcilient par HTTP mais les anciennes évaluations devront être refaites. Après perte complète de l’état, les offres retrouvées à distance sont considérées déjà notifiées pour éviter une vague d’anciens emails. Une reprise avec évaluation encore présente conserve au contraire la notification en attente. [Artefacts GitHub](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts).

## Structure

```text
aggregator/      Collecte, filtre, évaluation, SQLite local, client HTTP et SMTP
scripts/         Restauration de l'état GitHub Actions
tests/           Tests sans réseau, avec doubles HTTP
.github/         CI et collecte planifiée
config.toml      Critères et limites
profile.example.txt
```

Aucun code Python partagé, aucune base partagée et aucun sous-module entre les deux dépôts. Les scripts ne s'inscrivent pas automatiquement dans ton compte GitHub et aucun secret n'est fourni dans cette archive.

Résultats détaillés : [VERIFICATION.md](VERIFICATION.md). Le workflow attend les chemins par défaut `state/aggregator.db` et `config.toml` ; adapter sa restauration et sa sauvegarde si ces chemins changent.
