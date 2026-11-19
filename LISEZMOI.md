# SignalBourse : ton appli de signaux boursiers

Un tableau de bord qui s'ouvre dans ton navigateur, sur ton PC ou ton téléphone, sans passer par Claude. Il a trois onglets :
- **Ma liste** : tes ETF, obligations et actions, avec un signal court terme et un signal long terme, un stop, un objectif et la quantité maximale à acheter.
- **💎 Pépites** : les 12 meilleures petites et moyennes valeurs et ETF thématiques du moment (défense, semi-conducteurs, IA, uranium, robotique, Inde, cybersécurité…), sélectionnées parmi 34.
- **Méthode** : comment chaque score est calculé.

Tu as deux façons de l'utiliser. Tu peux faire les deux.

---

## Option A : sur ton PC (5 minutes)

1. Installe Python : https://www.python.org/downloads/ et coche bien **« Add Python to PATH »** pendant l'installation.
2. Dézippe le dossier `SignalBourse` (par exemple dans Documents).
3. **Double-clique sur `OUVRIR_SIGNALBOURSE.bat`** (sur Mac : `OUVRIR_SIGNALBOURSE_Mac.command`).

Le tableau de bord s'ouvre dans ton navigateur à l'adresse **http://localhost:8765**. Il se met à jour tout seul toutes les 15 minutes tant que la fenêtre noire reste ouverte. La première analyse prend 1 à 3 minutes.

📱 **Sur ton téléphone** : connecte-le au même Wi-Fi que ton PC et ouvre l'adresse affichée dans la fenêtre noire (du type `http://192.168.1.20:8765`). Dans le menu de ton navigateur, choisis « Ajouter à l'écran d'accueil » : tu auras une icône comme une vraie appli.

---

## Option B : en ligne 24h/24, sans laisser ton PC allumé (gratuit, 15 minutes)

GitHub fait tourner le programme pour toi 4 fois par jour en semaine et publie le tableau de bord à une adresse fixe, du type `https://ton-pseudo.github.io/signalbourse`. Tu l'ouvres de n'importe où, même depuis ton téléphone en 4G.

1. Crée un compte gratuit sur https://github.com.
2. Clique sur **New repository**, nomme-le `signalbourse`, choisis **Public**, puis **Create**.
3. Clique sur **uploading an existing file** et glisse **tout le contenu** du dossier SignalBourse, y compris le dossier caché `.github`. S'il n'apparaît pas, active l'affichage des fichiers cachés. Valide avec **Commit changes**.
   *Si le dossier `.github` n'a pas été envoyé* : clique sur **Add file > Create new file**, tape le nom `.github/workflows/signalbourse.yml`, colle le contenu du fichier `signalbourse_workflow.yml` fourni dans le dossier, puis valide avec **Commit changes**.
4. Va dans **Settings > Actions > General**, tout en bas, et coche **Read and write permissions**, puis **Save**.
5. Va dans l'onglet **Actions**, ouvre « SignalBourse - mise à jour automatique » et clique sur **Run workflow**. Attends 3 à 5 minutes.
6. Va dans **Settings > Pages**. Dans « Source », choisis **Deploy from a branch**, puis la branche **main** et le dossier **/docs**, et clique sur **Save**.
7. Une minute plus tard, ton adresse s'affiche en haut de la page Pages. Ajoute-la à l'écran d'accueil de ton téléphone.

La mise à jour se fait ensuite toute seule à 7h40, 12h10, 17h50 et 22h20 (heure de Paris, à une heure près selon l'heure d'été).

⚠️ Avec un compte GitHub gratuit, la page est **publique** : n'importe qui ayant l'adresse peut la voir. N'y mets pas tes vraies positions ni ton vrai capital. Le `capital_eur` de `config.json` sert seulement à calculer les quantités ; laisse une valeur fictive si tu préfères.

**Modifier ta liste en ligne** : sur GitHub, ouvre `config.json`, clique sur le crayon ✏️, modifie, puis **Commit changes**. La modification sera prise en compte à la prochaine mise à jour.

---

## Alertes sur ton téléphone (Telegram, optionnel)

1. Sur Telegram, parle à **@BotFather**, tape `/newbot` et récupère le *token*.
2. Envoie un message à ton nouveau bot, puis ouvre `https://api.telegram.org/bot<TOKEN>/getUpdates` et note ton `chat_id`.
3. Ensuite, selon l'option que tu utilises :
   - **Option A** : colle le token et le chat_id dans `config.json` > `alertes`.
   - **Option B** : sur GitHub, va dans **Settings > Secrets and variables > Actions > New repository secret** et crée `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`. Ne les mets pas dans `config.json`, car ce fichier est public.

Tu reçois alors un message quand un signal change, quand un titre approche de son stop, et un résumé des pépites à chaque mise à jour.

---

## Commandes avancées (terminal)
| Ce que tu veux | Commande |
|---|---|
| L'appli (comme le double-clic) | `python signal_bourse.py app` |
| Une analyse unique, puis ouverture du tableau de bord | `python signal_bourse.py analyse` |
| Analyser 1 ou 2 titres | `python signal_bourse.py analyse NVDA MC.PA` |
| Classement des pépites dans le terminal | `python signal_bourse.py pepites` |
| Tester la stratégie sur 5 ans | `python signal_bourse.py backtest MC.PA` |
| Ajouter ou retirer un titre | `python signal_bourse.py ajoute RMS.PA "Hermès" Action` / `retire GOOGL` |

**Ajouter une pépite à surveiller** : dans `config.json`, ajoute une ligne dans `"pepites"`, par exemple `{"ticker": "ALXXX.PA", "nom": "…", "type": "Action", "theme": "…"}`.
**Tickers** : ce sont ceux de Yahoo Finance. Paris = `.PA`, Amsterdam = `.AS`, Francfort / Xetra = `.DE`, Milan = `.MI`, Londres = `.L`, et rien pour les valeurs américaines. Si un ticker est introuvable, il apparaît dans l'onglet Méthode : corrige-le en cherchant le nom sur finance.yahoo.com.

## Comment lire les signaux
| Score | Signal |
|---|---|
| ≥ +0,45 | ACHAT FORT |
| +0,18 à +0,45 | ACHAT / RENFORCER |
| −0,18 à +0,18 | CONSERVER / ATTENDRE |
| −0,45 à −0,18 | ALLÉGER |
| ≤ −0,45 | VENDRE |

Le **score pépite** combine la dynamique du cours (6 et 12 mois), la tendance de fond, la distance au plus haut, la croissance du chiffre d'affaires et des bénéfices, la rentabilité, le potentiel selon les analystes, le PEG et la taille de l'entreprise. Plus il y a d'étoiles, plus le profil est fort, mais le **niveau de risque** affiché compte tout autant.

## À savoir
- Les pépites sont **beaucoup plus volatiles** que les grandes valeurs : elles peuvent perdre 30 à 50 % en quelques semaines. Les biotechs de la liste sont marquées « très risqué ». Une règle simple : 1 à 2 % du capital maximum par pépite, et 10 à 15 % au total.
- Un score élevé veut souvent dire que le titre a **déjà beaucoup monté**. Combine-le avec le signal court terme pour éviter d'acheter au plus haut.
- Les données Yahoo gratuites peuvent avoir 15 minutes de retard. L'éligibilité au PEA des ETF et actions étrangères est à vérifier chez ton courtier.
- **Conformité** : en tant que salarié BNP Paribas, respecte la politique de la banque sur les transactions personnelles. N'utilise jamais une information non publique sur un client.
- Outil d'aide à la décision, **pas un conseil en investissement**. Aucun signal n'est garanti.
