# SignalBourse : ton tableau de bord boursier mondial

Adresse : **https://holdingismaelkouloumba.github.io/signalbourse/** (protégée par mot de passe une fois le secret `SITE_PASSWORD` créé).

## Ce que contient le tableau de bord
| Onglet | Contenu | Mise à jour |
|---|---|---|
| **Ma liste** | Tes ETF, obligations et actions : signal court terme et signal long terme, stop, objectif, quantité max | Toutes les heures |
| **🌍 Opportunités monde** | Moyennes et grandes capitalisations de 30 pays (Amériques, Europe, Asie, Afrique du Sud, Égypte, Golfe…) avec une forte perspective de croissance, plus les ETF mondiaux les plus dynamiques. Badge 🆕 pour les nouvelles entrées, 🏦 quand un grand fonds vient d'acheter le titre | **Liste renouvelée chaque jour**, cours toutes les heures |
| **💎 Pépites** | Petites et moyennes valeurs plus risquées : ta liste perso plus celles détectées automatiquement | Chaque jour / chaque heure |
| **🛢️ Matières & Forex** | Or, argent, platine, cuivre, pétrole, gaz, blé, maïs, café, cacao, sucre ; EUR/USD, USD/JPY, GBP/USD, rand, naira, dirham, bitcoin… | Toutes les heures |
| **🏦 Grands fonds** | Nouvelles positions, renforcements, allègements et ventes de Buffett, Ackman, Tepper, Druckenmiller, Burry, Dalio, Tiger Global, Coatue, Fundsmith, Baillie Gifford | Chaque semaine (les données sont trimestrielles) |

Calendrier : toutes les heures de 7h à 22h en semaine (heure de Paris), une fois par jour le week-end.
Newsletters par e-mail : **lundi 7h40** (« Ta semaine ») et **vendredi 18h10** (« Bilan de la semaine »).

---

## Les réglages à faire une seule fois (secrets GitHub)

Les secrets sont invisibles pour les autres, même si le dépôt est public.
Pour les créer : **github.com/holdingIsmaelKOULOUMBA/signalbourse/settings/secrets/actions**, puis **New repository secret** (sur téléphone, passe d'abord le navigateur en « version ordinateur »).

| Nom du secret (à écrire exactement) | Valeur | À quoi ça sert |
|---|---|---|
| `SITE_PASSWORD` | Le mot de passe de ton choix | Protège l'accès au site |
| `SMTP_USER` | Ton adresse Gmail | Expéditeur des newsletters |
| `SMTP_PASSWORD` | Un « mot de passe d'application » Gmail (voir ci-dessous) | Envoi des newsletters |
| `EMAIL_TO` | L'adresse qui reçoit les newsletters (peut être la même) | Destinataire |
| `TELEGRAM_BOT_TOKEN` | Le token donné par @BotFather | Alertes sur ton téléphone |
| `TELEGRAM_CHAT_ID` | Ton Id donné par @userinfobot | Alertes sur ton téléphone |

**Créer le mot de passe d'application Gmail (gratuit)**
1. Active la validation en deux étapes sur ton compte Google : myaccount.google.com > Sécurité.
2. Ouvre **myaccount.google.com/apppasswords**, donne un nom (par exemple « SignalBourse »), puis **Créer**.
3. Google affiche un code de 16 lettres : c'est la valeur de `SMTP_PASSWORD`. N'utilise jamais ton vrai mot de passe Gmail.

**Tester une newsletter tout de suite** : onglet **Actions** > « SignalBourse - mise à jour automatique » > **Run workflow** > écris `lundi` ou `bilan` dans la case > **Run workflow**.

---

## Modifier tes listes
Sur GitHub, ouvre `config.json`, clique sur le crayon ✏️, modifie, puis **Commit changes**.
- `"watchlist"` = Ma liste.
- `"pepites"` = tes pépites perso.

Les opportunités monde, les ETF mondiaux, les matières premières et les devises se renouvellent seuls : rien à faire.

## Utiliser l'appli sur ton PC (optionnel)
Installe Python 3.12 ou plus récent (coche « Add Python to PATH »), puis double-clique sur `OUVRIR_SIGNALBOURSE.bat`.

## Comment les scores sont calculés
- **Court terme** (jours / semaines) : tendance récente, RSI, MACD, Bollinger, momentum, actualités des 14 derniers jours, achats et ventes des dirigeants.
- **Long terme** (mois / années) : bilan (croissance, marges, rentabilité, dette, trésorerie), valorisation (PER, PEG), avis et objectifs des analystes, tendance de fond, actualités, dirigeants.
- **Score croissance** : dynamique du cours sur 6 et 12 mois, croissance du chiffre d'affaires et des bénéfices, rentabilité, potentiel, PEG, taille de l'entreprise, plus un bonus si un grand fonds a acheté le titre.

| Score | Signal |
|---|---|
| ≥ +0,45 | ACHAT FORT |
| +0,18 à +0,45 | ACHAT / RENFORCER |
| −0,18 à +0,18 | CONSERVER / ATTENDRE |
| −0,45 à −0,18 | ALLÉGER |
| ≤ −0,45 | VENDRE |

## Limites à connaître
- Données gratuites de Yahoo Finance (usage personnel, jusqu'à 15 minutes de retard) et de la SEC.
- Afrique : seules les bourses de Johannesburg et du Caire sont couvertes gratuitement. La BRVM, la BVMAC, Lagos et Casablanca ne le sont pas.
- Les positions des grands fonds sont publiées avec environ 45 jours de retard.
- Les ETF américains de l'onglet Monde ne sont pas éligibles au PEA : il faut un compte-titres.
- Le dépôt GitHub est public : le site est protégé par mot de passe, mais les fichiers de données du dépôt (historique, listes) restent lisibles par qui les cherche.
- **Conformité** : en tant que salarié BNP Paribas, respecte la politique de la banque sur les transactions personnelles. N'utilise jamais une information non publique sur un client.
- Outil d'aide à la décision, **pas un conseil en investissement**. Aucun signal n'est garanti.
