#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalBourse : analyse de marché et signaux d'achat / vente (court terme et long terme)

Commandes :
  python signal_bourse.py app                -> L'APPLI : tableau de bord dans ton navigateur, mis à jour en continu
                                                (accessible aussi depuis ton téléphone sur le même Wi-Fi)
  python signal_bourse.py analyse            -> une analyse complète (liste + pépites) et ouvre le tableau de bord
  python signal_bourse.py analyse NVDA MC.PA -> analyse seulement ces titres
  python signal_bourse.py pepites            -> classe les pépites (petites/moyennes valeurs et ETF thématiques)
  python signal_bourse.py surveille          -> tourne en continu et envoie des alertes (Telegram) quand un signal change
  python signal_bourse.py site               -> génère le site docs/index.html (version en ligne via GitHub)
  python signal_bourse.py idees              -> scanne ~50 grandes valeurs et classe les meilleures idées
  python signal_bourse.py backtest MC.PA     -> teste la stratégie court terme sur 5 ans d'historique
  python signal_bourse.py ajoute TICKER "Nom" [Type]   -> ajoute un titre à ta liste
  python signal_bourse.py retire TICKER      -> retire un titre

IMPORTANT : outil d'aide à la décision. Ce n'est pas un conseil en investissement.
Aucun signal n'est garanti. Les performances passées ne préjugent pas des performances futures.
"""

import json
import os
import math
import re
import sys
import time
import html
import datetime as dt
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

DOSSIER = Path(__file__).resolve().parent
CONFIG = DOSSIER / "config.json"
SORTIE = DOSSIER / "rapports"
HISTO = DOSSIER / "historique_signaux.csv"
ETAT = DOSSIER / "derniers_signaux.json"

AVERTISSEMENT = ("Outil d'aide à la décision, pas un conseil en investissement. "
                 "Aucun signal n'est garanti ; tu peux perdre tout ou partie du capital investi.")

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

def charger_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def sauver_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# Récupération des données
# ----------------------------------------------------------------------------

def _exiger_yf():
    if yf is None:
        sys.exit("Il manque yfinance. Lance : pip install -r requirements.txt")


def historique(ticker, periode="5y"):
    _exiger_yf()
    h = yf.Ticker(ticker).history(period=periode, auto_adjust=True)
    if h is None or h.empty:
        raise ValueError(f"Pas de données de cours pour {ticker} (vérifie le ticker sur finance.yahoo.com)")
    h.index = pd.to_datetime(h.index).tz_localize(None)
    return h[["Open", "High", "Low", "Close", "Volume"]].dropna()


def infos_fondamentales(ticker):
    _exiger_yf()
    try:
        brut = yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    propre = {}
    for k, v in brut.items():
        if isinstance(v, str) and k not in ("currency", "longName", "shortName", "sector", "industry", "country"):
            try:
                v = float(v)
            except ValueError:
                continue  # valeur texte inattendue pour un champ numérique : ignorée
        propre[k] = v
    return propre


def transactions_dirigeants(ticker):
    """Achats / ventes d'actions par les dirigeants (surtout dispo pour les actions US)."""
    _exiger_yf()
    try:
        df = yf.Ticker(ticker).insider_transactions
        if df is None or df.empty:
            return None
        return df
    except Exception:
        return None


def _lire_rss(url, maxi=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SignalBourse"})
    with urllib.request.urlopen(req, timeout=10) as r:
        racine = ET.fromstring(r.read())
    sortie = []
    for item in racine.iter("item"):
        titre = (item.findtext("title") or "").strip()
        lien = (item.findtext("link") or "").strip()
        date = (item.findtext("pubDate") or "").strip()
        if titre:
            sortie.append({"titre": titre, "lien": lien, "date": date})
        if len(sortie) >= maxi:
            break
    return sortie


def actualites(ticker, nom):
    """Actualités : Yahoo Finance + Google News (FR et EN), sur les 14 derniers jours."""
    news = []
    if yf is not None:
        try:
            for n in (yf.Ticker(ticker).news or [])[:15]:
                c = n.get("content", n)
                titre = c.get("title", "")
                lien = (c.get("canonicalUrl") or {}).get("url", "") if isinstance(c.get("canonicalUrl"), dict) else c.get("link", "")
                date = c.get("pubDate", "") or c.get("providerPublishTime", "")
                if titre:
                    news.append({"titre": titre, "lien": lien, "date": str(date)})
        except Exception:
            pass
    nom_court = re.sub(r"\(.*?\)", "", nom).strip()
    for langue, pays in (("fr", "FR"), ("en", "US")):
        q = urllib.parse.quote(f'"{nom_court}" when:14d')
        url = f"https://news.google.com/rss/search?q={q}&hl={langue}&gl={pays}&ceid={pays}:{langue}"
        try:
            news += _lire_rss(url)
        except Exception:
            pass
    vus, uniques = set(), []
    for n in news:
        cle = n["titre"].lower()[:80]
        if cle not in vus:
            vus.add(cle)
            uniques.append(n)
    return uniques[:30]


# ----------------------------------------------------------------------------
# Analyse de l'actualité (sentiment + événements liés aux dirigeants)
# ----------------------------------------------------------------------------

MOTS_POSITIFS = {
    # anglais
    "beat": 2, "beats": 2, "tops": 2, "record": 1, "surge": 2, "soar": 2, "soars": 2, "jumps": 2,
    "raises guidance": 3, "raises outlook": 3, "upgrade": 2, "upgraded": 2, "outperform": 2,
    "buyback": 2, "share repurchase": 2, "dividend increase": 2, "raises dividend": 2,
    "strong demand": 2, "contract": 1, "partnership": 1, "approval": 2, "approved": 2,
    "growth": 1, "profit rises": 2, "wins": 1, "rally": 1, "acquire": 1,
    # français
    "hausse": 1, "bondit": 2, "s'envole": 2, "record": 1, "relève": 2, "relève ses prévisions": 3,
    "dépasse": 2, "supérieur aux attentes": 3, "rachat d'actions": 2, "dividende en hausse": 2,
    "contrat": 1, "partenariat": 1, "croissance": 1, "bénéfice en hausse": 2, "relèvement": 2,
    "acheter": 1, "surperformance": 2, "succès": 1, "commande": 1,
}
MOTS_NEGATIFS = {
    "miss": 2, "misses": 2, "plunge": 3, "plunges": 3, "falls": 1, "drops": 1, "slump": 2,
    "cuts guidance": 3, "lowers outlook": 3, "downgrade": 2, "downgraded": 2, "underperform": 2,
    "lawsuit": 2, "probe": 2, "investigation": 2, "fraud": 3, "recall": 2, "fine": 1,
    "layoffs": 1, "warning": 2, "profit warning": 3, "loss": 1, "tariff": 1, "antitrust": 2,
    "resigns": 2, "steps down": 2, "ousted": 3, "bankruptcy": 3, "default": 3, "strike": 1,
    "baisse": 1, "chute": 2, "plonge": 3, "recule": 1, "abaisse": 2, "abaisse ses prévisions": 3,
    "avertissement": 2, "inférieur aux attentes": 3, "enquête": 2, "amende": 2, "procès": 2,
    "démission": 2, "démissionne": 2, "grève": 1, "perte": 1, "licenciements": 1, "rappel": 2,
    "droits de douane": 1, "vendre": 1, "dégradation": 2, "faillite": 3,
}
MOTS_DIRIGEANTS = [
    "ceo", "chief executive", "cfo", "chairman", "board", "management", "insider",
    "pdg", "directeur général", "président", "dirigeant", "conseil d'administration",
    "directoire", "nomination", "appoints", "appointed", "succession", "steps down",
    "démission", "resigns", "acquisition", "merger", "fusion", "rachat", "buyback",
    "guidance", "prévisions", "dividend", "dividende", "stratégie", "strategy", "plan",
]


def score_texte(titre):
    t = titre.lower()
    s = 0
    for mot, p in MOTS_POSITIFS.items():
        if mot in t:
            s += p
    for mot, p in MOTS_NEGATIFS.items():
        if mot in t:
            s -= p
    return s


def analyser_actualites(news):
    if not news:
        return {"score": 0.0, "nb": 0, "positives": [], "negatives": [], "dirigeants": []}
    notes = []
    pos, neg, dirig = [], [], []
    for n in news:
        s = score_texte(n["titre"])
        poids = 1.5 if any(m in n["titre"].lower() for m in MOTS_DIRIGEANTS) else 1.0
        notes.append(s * poids)
        if poids > 1:
            dirig.append(n)
        if s > 0:
            pos.append(n)
        elif s < 0:
            neg.append(n)
    brut = sum(notes) / max(len(notes), 1)
    score = float(np.tanh(brut / 1.5))  # ramené entre -1 et +1
    return {"score": score, "nb": len(news), "positives": pos[:5], "negatives": neg[:5], "dirigeants": dirig[:5]}


def analyser_dirigeants(df):
    """Score des transactions de dirigeants sur 6 mois : achats = positif, ventes massives = négatif."""
    if df is None or df.empty:
        return {"score": 0.0, "texte": "Pas de données sur les achats et ventes d'actions des dirigeants"}
    try:
        d = df.copy()
        col_date = next((c for c in d.columns if "date" in c.lower()), None)
        if col_date:
            d[col_date] = pd.to_datetime(d[col_date], errors="coerce")
            d = d[d[col_date] > pd.Timestamp.now() - pd.Timedelta(days=180)]
        texte = (d.get("Text", d.get("Transaction", pd.Series(dtype=str))).astype(str).str.lower())
        achats = texte.str.contains("purchase|buy|achat").sum()
        ventes = texte.str.contains("sale|sell|vente").sum()
        total = achats + ventes
        if total == 0:
            return {"score": 0.0, "texte": "Aucun achat ni vente d'actions par les dirigeants récemment"}
        score = (achats - ventes) / total
        # Les ventes de dirigeants sont fréquentes (rémunération), on atténue le négatif
        if score < 0:
            score *= 0.4
        return {"score": float(score), "texte": f"Sur 6 mois, les dirigeants ont acheté {achats} fois et vendu {ventes} fois des actions de leur entreprise"}
    except Exception:
        return {"score": 0.0, "texte": "Données de dirigeants illisibles"}


# ----------------------------------------------------------------------------
# Indicateurs techniques
# ----------------------------------------------------------------------------

def indicateurs(h):
    d = h.copy()
    c = d["Close"]
    d["SMA20"] = c.rolling(20).mean()
    d["SMA50"] = c.rolling(50).mean()
    d["SMA200"] = c.rolling(200).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    perte = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / perte.replace(0, np.nan)
    d["RSI"] = 100 - 100 / (1 + rs)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    d["MACD"] = ema12 - ema26
    d["MACD_signal"] = d["MACD"].ewm(span=9, adjust=False).mean()
    d["MACD_hist"] = d["MACD"] - d["MACD_signal"]
    std20 = c.rolling(20).std()
    d["BB_haut"] = d["SMA20"] + 2 * std20
    d["BB_bas"] = d["SMA20"] - 2 * std20
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - c.shift()).abs(), (d["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.rolling(14).mean()
    d["Vol_moy20"] = d["Volume"].rolling(20).mean()
    d["Rdt"] = c.pct_change()
    return d


def score_technique_ct(d):
    """Score court terme (jours / semaines) entre -1 et +1, calculé ligne par ligne (sert aussi au backtest)."""
    c = d["Close"]
    s = pd.Series(0.0, index=d.index)
    s += np.where(c > d["SMA20"], 0.15, -0.15)
    s += np.where(d["SMA20"] > d["SMA50"], 0.15, -0.15)
    s += np.where(d["MACD_hist"] > 0, 0.15, -0.15)
    s += np.where(d["MACD_hist"] > d["MACD_hist"].shift(), 0.10, -0.10)
    rsi = d["RSI"]
    s += np.select([rsi < 30, rsi < 45, rsi > 75, rsi > 65], [0.20, 0.05, -0.20, -0.05], 0.0)
    mom = c / c.shift(20) - 1
    s += np.clip(mom * 2, -0.15, 0.15)
    pos_bb = (c - d["BB_bas"]) / (d["BB_haut"] - d["BB_bas"])
    s += np.select([pos_bb < 0.05, pos_bb > 0.95], [0.10, -0.10], 0.0)
    return s.clip(-1, 1)


def score_technique_lt(d):
    c = d["Close"]
    s = pd.Series(0.0, index=d.index)
    s += np.where(c > d["SMA200"], 0.35, -0.35)
    s += np.where(d["SMA50"] > d["SMA200"], 0.25, -0.25)
    mom12 = c.shift(21) / c.shift(252) - 1  # momentum 12 mois hors dernier mois
    s += np.clip(mom12, -0.4, 0.4)
    return s.clip(-1, 1)


# ----------------------------------------------------------------------------
# Analyse du bilan (expliquée en mots simples)
# ----------------------------------------------------------------------------

def _f(info, *cles):
    """Premier champ numérique disponible parmi les clés données."""
    for c in cles:
        v = info.get(c)
        if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            return float(v)
    return None


def avis_analystes(info):
    reco, nb = _f(info, "recommendationMean"), _f(info, "numberOfAnalystOpinions")
    if not reco:
        return None
    mot = ("achat fort" if reco <= 1.6 else "achat" if reco <= 2.4 else "neutre" if reco <= 3.2
           else "plutôt vente" if reco <= 4 else "vente")
    return f"Avis des analystes : {mot}" + (f" ({int(nb)} analystes)" if nb else "")


def score_fondamental(info, type_titre):
    """Santé de l'entreprise (bilan + valorisation) : score de -1 à +1 et explications en mots simples."""
    if type_titre != "Action" or not info:
        return 0.0, ["Pas de bilan à analyser pour ce type de produit (ETF, obligations, matière première, devise ou crypto)"]
    notes, raisons = [], []

    def ajoute(note, texte):
        notes.append(note)
        raisons.append(texte)

    pe = _f(info, "forwardPE", "trailingPE")
    if pe is not None:
        if pe < 0:
            ajoute(-0.5, "L'entreprise perd de l'argent pour l'instant")
        elif pe < 12:
            ajoute(0.5, f"Prix très raisonnable : tu paies {pe:.0f} fois son bénéfice annuel")
        elif pe < 25:
            ajoute(0.2, f"Prix raisonnable : tu paies {pe:.0f} fois son bénéfice annuel")
        elif pe < 45:
            ajoute(-0.2, f"Prix élevé : tu paies {pe:.0f} fois son bénéfice annuel")
        else:
            ajoute(-0.5, f"Prix très élevé : tu paies {pe:.0f} fois son bénéfice annuel (beaucoup d'espoir déjà intégré)")
    peg = _f(info, "trailingPegRatio", "pegRatio")
    if peg and peg > 0:
        if peg < 1.2:
            ajoute(0.4, "Prix bon marché par rapport à la croissance attendue")
        elif peg < 2.5:
            ajoute(0.0, "Prix correct par rapport à la croissance attendue")
        else:
            ajoute(-0.4, "Prix cher par rapport à la croissance attendue")
    cr = _f(info, "revenueGrowth")
    if cr is not None:
        ajoute(float(np.clip(cr * 4, -0.6, 0.6)), f"Chiffre d'affaires : {cr:+.0%} sur un an")
    cb = _f(info, "earningsGrowth")
    if cb is not None:
        ajoute(float(np.clip(cb * 2, -0.6, 0.6)), f"Bénéfices : {cb:+.0%} sur un an")
    marge = _f(info, "profitMargins")
    if marge is not None:
        qualif = "très rentable" if marge > 0.2 else "rentable" if marge > 0.08 else "peu rentable" if marge > 0 else "pas rentable"
        ajoute(0.4 if marge > 0.2 else 0.1 if marge > 0.08 else -0.3,
               f"Garde {marge * 100:.0f} € de bénéfice pour 100 € de ventes ({qualif})")
    roe = _f(info, "returnOnEquity")
    if roe is not None:
        qualif = "excellente" if roe > 0.18 else "correcte" if roe > 0.10 else "faible"
        ajoute(0.4 if roe > 0.18 else 0.1 if roe > 0.10 else -0.3,
               f"Rapporte {roe * 100:.0f} % par an sur l'argent investi par les actionnaires ({qualif})")
    de = _f(info, "debtToEquity")
    if de is not None:
        ajoute(0.2 if de < 60 else 0 if de < 150 else -0.4,
               "Endettement faible" if de < 60 else "Endettement modéré" if de < 150 else "Endettement élevé")
    fcf = _f(info, "freeCashflow")
    if fcf is not None:
        ajoute(0.2 if fcf > 0 else -0.4, "Génère de l'argent après avoir payé ses investissements" if fcf > 0
               else "Dépense plus d'argent qu'elle n'en génère")
    reco = _f(info, "recommendationMean")
    if reco:
        notes.append(float(np.clip((3 - reco) / 2, -0.6, 0.6)))
        raisons.append(avis_analystes(info))
    cible, prix = _f(info, "targetMeanPrice"), _f(info, "currentPrice", "regularMarketPrice")
    if cible and prix:
        pot = cible / prix - 1
        ajoute(float(np.clip(pot * 2, -0.5, 0.5)), f"Objectif moyen des analystes : {pot:+.0%} par rapport au cours actuel")
    div = _f(info, "dividendYield")
    if div:
        div = div / 100 if div > 1 else div
        raisons.append(f"Verse un dividende d'environ {div:.1%} par an")
    if not notes:
        return 0.0, ["Données de bilan indisponibles"]
    return float(np.clip(np.mean(notes) * 1.6, -1, 1)), raisons


# ----------------------------------------------------------------------------
# Décision
# ----------------------------------------------------------------------------

def libelle(score):
    if score >= 0.45:
        return "ACHAT FORT"
    if score >= 0.18:
        return "ACHAT / RENFORCER"
    if score > -0.18:
        return "CONSERVER / ATTENDRE"
    if score > -0.45:
        return "ALLÉGER"
    return "VENDRE"


def raisons_techniques(d):
    der = d.iloc[-1]
    r = []
    c = der["Close"]
    if not np.isnan(der["SMA200"]):
        r.append("Tendance de fond en hausse : le cours est au-dessus de sa moyenne des 200 derniers jours" if c > der["SMA200"]
                 else "Tendance de fond en baisse : le cours est sous sa moyenne des 200 derniers jours")
    r.append("Tendance des dernières semaines positive" if der["SMA20"] > der["SMA50"] else "Tendance des dernières semaines négative")
    rsi = der["RSI"]
    if rsi > 70:
        r.append("A beaucoup monté très vite : une petite baisse à court terme est fréquente après ça")
    elif rsi < 30:
        r.append("A beaucoup baissé très vite : un rebond est possible")
    else:
        r.append("Pas de surchauffe : le rythme de hausse ou de baisse est normal")
    r.append("L'élan des derniers jours s'améliore" if der["MACD_hist"] > 0 else "L'élan des derniers jours faiblit")
    if der["Volume"] > 2 * (der["Vol_moy20"] or 1):
        r.append("Beaucoup plus d'échanges que d'habitude : mouvement à prendre au sérieux")
    return r


def score_potentiel(d, info, type_titre, perf):
    """Potentiel de hausse À VENIR (et pas seulement ce qui a déjà monté) : croissance attendue, qualité,
    prix raisonnable et bon moment d'achat. Score de -1 à +1 avec explications simples."""
    c = d["Close"]
    der = d.iloc[-1]
    notes, raisons = [], []
    sma200 = der["SMA200"]
    ecart200 = float(c.iloc[-1] / sma200 - 1) if not np.isnan(sma200) else None
    plus_haut = float(c.tail(252).max())
    decote = float(c.iloc[-1] / plus_haut - 1)
    m12 = perf.get("1 an")

    # --- Croissance attendue et qualité (actions)
    if type_titre == "Action" and info:
        fe, te = _f(info, "forwardEps"), _f(info, "trailingEps")
        if fe and te and te > 0:
            g = fe / te - 1
            notes.append(float(np.clip(g * 2, -0.6, 0.8)))
            raisons.append(f"Les analystes attendent des bénéfices {g:+.0%} l'an prochain")
        cr = _f(info, "revenueGrowth")
        if cr is not None:
            notes.append(float(np.clip(cr * 2.5, -0.6, 0.8)))
            raisons.append(f"Ventes en {'hausse' if cr >= 0 else 'baisse'} de {abs(cr):.0%} sur un an")
        cible, prix = _f(info, "targetMeanPrice"), _f(info, "currentPrice", "regularMarketPrice")
        nb = _f(info, "numberOfAnalystOpinions") or 0
        if cible and prix and nb >= 3:
            pot = cible / prix - 1
            notes.append(float(np.clip(pot * 2, -0.5, 0.8)))
            raisons.append(f"Les analystes voient {pot:+.0%} de potentiel ({int(nb)} avis)")
        roe, marge, fcf = _f(info, "returnOnEquity"), _f(info, "profitMargins"), _f(info, "freeCashflow")
        qualite = sum([(roe or 0) > 0.15, (marge or 0) > 0.10, (fcf or 0) > 0])
        notes.append([-0.3, 0.0, 0.2, 0.4][qualite])
        raisons.append(["Entreprise encore fragile (peu ou pas rentable)", "Qualité moyenne",
                        "Entreprise de bonne qualité", "Entreprise de grande qualité (rentable et génère de l'argent)"][qualite])
        peg = _f(info, "trailingPegRatio", "pegRatio")
        if peg and peg > 0:
            notes.append(0.35 if peg < 1.3 else 0.0 if peg < 2.5 else -0.35)
            if peg < 1.3:
                raisons.append("Sa croissance n'est pas encore payée cher : bon rapport croissance / prix")
        cap = _f(info, "marketCap")
        if cap and cap < 10e9 * 1.2:
            notes.append(0.1)
            raisons.append("Taille moyenne : plus de place pour grandir que les géants")
        # décote sur une entreprise solide = opportunité
        if decote < -0.25 and qualite >= 2:
            notes.append(0.25)
            raisons.append(f"Cours {abs(decote):.0%} sous son plus haut d'un an alors que l'entreprise reste solide : possible opportunité")
    else:
        # --- ETF, matières premières, devises, cryptos : qualité de la tendance
        m6 = float(c.iloc[-1] / c.iloc[-127] - 1) if len(c) > 127 else None
        if m6 is not None:
            notes.append(float(np.clip(m6, -0.5, 0.5)))
            raisons.append(f"Évolution sur 6 mois : {m6:+.0%}")
        if decote < -0.30:
            notes.append(0.1)
            raisons.append(f"Encore {abs(decote):.0%} sous son plus haut d'un an : marge de remontée")

    # --- Moment d'achat (pour tous)
    sma50_monte = len(d) > 20 and d["SMA50"].iloc[-1] > d["SMA50"].iloc[-20]
    if ecart200 is not None:
        recent_croisement = bool((c.tail(60) < d["SMA200"].tail(60)).any()) and ecart200 > 0
        if recent_croisement and sma50_monte:
            notes.append(0.4)
            raisons.append("Le cours commence tout juste à remonter au-dessus de sa tendance de fond : bon moment potentiel")
        elif 0 < ecart200 < 0.25 and sma50_monte:
            notes.append(0.25)
            raisons.append("Tendance de hausse saine, sans emballement")
        elif ecart200 >= 0.40:
            notes.append(-0.35)
            raisons.append(f"A déjà beaucoup monté ({ecart200:.0%} au-dessus de sa moyenne de fond) : attendre un repli serait plus prudent")
        elif ecart200 < -0.10 and not sma50_monte:
            notes.append(-0.3)
            raisons.append("Toujours en baisse : mieux vaut attendre des signes de reprise")
    if der["RSI"] > 75:
        notes.append(-0.2)
        raisons.append("Surchauffe à court terme : risque de petite baisse")
    if m12 is not None and m12 > 1.2:
        notes.append(-0.2)
        raisons.append(f"Déjà {m12:+.0%} en un an : une partie du potentiel est peut-être déjà dans le prix")
    if not notes:
        return 0.0, ["Données insuffisantes"]
    return float(np.clip(np.mean(notes) * 1.6, -1, 1)), raisons


# compatibilité avec le reste du programme
score_pepite = score_potentiel


def niveau_risque(vol):
    if vol is None or np.isnan(vol):
        return "inconnu"
    return "très élevé" if vol > 0.60 else "élevé" if vol > 0.40 else "moyen" if vol > 0.25 else "modéré"


EUROPE_PEA = {"France", "Germany", "Netherlands", "Belgium", "Italy", "Spain", "Portugal", "Ireland", "Austria",
              "Finland", "Sweden", "Denmark", "Norway", "Iceland", "Luxembourg", "Greece", "Poland", "Czech Republic",
              "Hungary", "Estonia", "Latvia", "Lithuania", "Slovenia", "Slovakia", "Croatia", "Romania", "Bulgaria",
              "Malta", "Cyprus", "Liechtenstein"}
PLACES_EUROPE = (".PA", ".AS", ".BR", ".MI", ".MC", ".DE", ".F", ".HE", ".CO", ".ST", ".OL", ".LS", ".VI", ".IR", ".AT", ".WA", ".PR")


def eligibilite_pea(ticker, type_titre, pays_siege, nom):
    if type_titre == "Action":
        if pays_siege in EUROPE_PEA and ticker.endswith(PLACES_EUROPE):
            return "PEA"
        return "Compte-titres"
    if type_titre in ("ETF", "Obligations", "Matières premières") and "PEA" in (nom or "").upper():
        return "PEA"
    if type_titre in ("ETF", "Obligations"):
        return "À vérifier"
    return "Compte-titres"


def analyser(entree, cfg, avec_news=True):
    ticker, nom, type_titre = entree["ticker"], entree.get("nom", entree["ticker"]), entree.get("type", "Action")
    h = historique(ticker, "5y")
    d = indicateurs(h)
    der = d.iloc[-1]
    prix = float(der["Close"])

    tech_ct = float(score_technique_ct(d).iloc[-1])
    tech_lt = float(score_technique_lt(d).fillna(0).iloc[-1])
    info = infos_fondamentales(ticker) if type_titre not in ("Forex",) else {}
    fond, raisons_f = score_fondamental(info, type_titre)
    news = actualites(ticker, entree.get("recherche") or nom) if avec_news else []
    an = analyser_actualites(news)
    dirig = analyser_dirigeants(transactions_dirigeants(ticker)) if type_titre == "Action" else {"score": 0, "texte": "—"}

    perf = {}
    for lib, n in (("1 sem.", 5), ("1 mois", 21), ("3 mois", 63), ("1 an", 252)):
        if len(h) > n:
            perf[lib] = float(h["Close"].iloc[-1] / h["Close"].iloc[-1 - n] - 1)
    pot, raisons_pot = score_potentiel(d, info, type_titre, perf)

    # Pondérations (profil dynamique / équilibré)
    score_ct = 0.70 * tech_ct + 0.25 * an["score"] + 0.05 * dirig["score"]
    if type_titre == "Action":
        score_lt = 0.35 * fond + 0.25 * pot + 0.25 * tech_lt + 0.10 * an["score"] + 0.05 * dirig["score"]
    else:
        score_lt = 0.45 * tech_lt + 0.40 * pot + 0.15 * an["score"]

    # Gestion du risque : seuil de protection et objectif selon la variation habituelle du cours
    variation = float(der["ATR"])
    stop = prix - 2 * variation
    objectif = prix + 3 * variation
    vol_annuelle = float(d["Rdt"].tail(252).std() * math.sqrt(252))
    risque_eur = cfg["capital_eur"] * cfg["risque_par_trade_pct"] / 100
    quantite = int(risque_eur / max(prix - stop, 1e-9))
    quantite = min(quantite, int(cfg["capital_eur"] * 0.15 / prix))  # jamais plus de 15 % du capital sur une ligne
    max_dd = float((h["Close"] / h["Close"].cummax() - 1).tail(252).min())
    pays_siege = info.get("country", "")
    div = _f(info, "dividendYield")
    if div and div > 1:
        div = div / 100

    deux_ans = d.tail(504)
    pas = max(1, len(deux_ans) // 260)
    courbe = {"dates": [x.strftime("%Y-%m-%d") for x in deux_ans.index[::pas]],
              "cours": [round(float(x), 4) for x in deux_ans["Close"].values[::pas]],
              "m50": [None if np.isnan(x) else round(float(x), 4) for x in deux_ans["SMA50"].values[::pas]],
              "m200": [None if np.isnan(x) else round(float(x), 4) for x in deux_ans["SMA200"].values[::pas]]}

    return {
        "ticker": ticker, "nom": nom, "type": type_titre, "prix": prix, "theme": entree.get("theme", ""),
        "pays": entree.get("pays", ""), "zone": entree.get("zone", ""), "secteur": entree.get("secteur", "") or info.get("sector", ""),
        "recherche": entree.get("recherche", ""), "code_pays": entree.get("code_pays", ""), "pays_siege": pays_siege,
        "pct_institutions": info.get("heldPercentInstitutions"),
        "pea": eligibilite_pea(ticker, type_titre, pays_siege, nom),
        "dividende": div, "avis_analystes": avis_analystes(info),
        "resume": (info.get("longBusinessSummary") or "")[:700], "site_web": info.get("website", ""),
        "score_pepite": round(pot, 3), "raisons_pepite": raisons_pot,
        "capitalisation": info.get("marketCap"),
        "devise": info.get("currency", "") or ("USD" if ticker.endswith("-USD") else ""), "date": str(d.index[-1].date()),
        "score_ct": round(score_ct, 3), "signal_ct": libelle(score_ct),
        "score_lt": round(score_lt, 3), "signal_lt": libelle(score_lt),
        "tech_ct": round(tech_ct, 3), "tech_lt": round(tech_lt, 3), "fondamental": round(fond, 3),
        "sentiment": round(an["score"], 3), "nb_news": an["nb"], "dirigeants": dirig,
        "raisons_tech": raisons_techniques(d), "raisons_fond": raisons_f,
        "news_pos": an["positives"], "news_neg": an["negatives"], "news_dirig": an["dirigeants"],
        "rsi": float(der["RSI"]), "stop": stop, "objectif": objectif, "quantite": quantite,
        "vol_annuelle": vol_annuelle, "max_dd_1an": max_dd, "perf": perf,
        "spark": [float(x) for x in h["Close"].tail(120).values], "courbe": courbe,
    }



# ----------------------------------------------------------------------------
# Tableau de bord HTML (s'ouvre dans n'importe quel navigateur, PC ou téléphone)
# ----------------------------------------------------------------------------

COULEURS = {"ACHAT FORT": "#0a7d32", "ACHAT / RENFORCER": "#3aa655", "CONSERVER / ATTENDRE": "#8a8a8a",
            "ALLÉGER": "#d98a1c", "VENDRE": "#c62828"}


def _spark_svg(vals, l=120, h=34):
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    e = (mx - mn) or 1
    pts = " ".join(f"{i * l / (len(vals) - 1):.1f},{h - (v - mn) / e * h:.1f}" for i, v in enumerate(vals))
    coul = "#0a7d32" if vals[-1] >= vals[0] else "#c62828"
    return f'<svg width="{l}" height="{h}" viewBox="0 0 {l} {h}"><polyline fill="none" stroke="{coul}" stroke-width="1.6" points="{pts}"/></svg>'


def _badge(sig):
    return f'<span class="badge" style="background:{COULEURS.get(sig, "#888")}">{html.escape(sig)}</span>'


def _liens(news):
    if not news:
        return "<em>—</em>"
    return "<br>".join(f'<a href="{html.escape(n["lien"])}" target="_blank" rel="noopener">{html.escape(n["titre"][:120])}</a>'
                       for n in news[:4])


def _perf(r):
    return " · ".join(f"{k} <b class='{'up' if v >= 0 else 'down'}'>{v:+.1%}</b>" for k, v in r["perf"].items())


def _carte_ligne(r):
    return f"""
<div class="carte" data-type="{html.escape(r['type'])}">
  <div class="haut">
    <div><div class="nom">{html.escape(r['nom'])}</div><div class="petit">{html.escape(r['ticker'])} · {html.escape(r['type'])}</div></div>
    <div class="prix">{r['prix']:.2f} <small>{html.escape(r['devise'])}</small><br>{_spark_svg(r['spark'])}</div>
  </div>
  <div class="petit">{_perf(r)}</div>
  <div class="signaux">
    <div><div class="petit">Court terme</div>{_badge(r['signal_ct'])}</div>
    <div><div class="petit">Long terme</div>{_badge(r['signal_lt'])}</div>
  </div>
  <div class="petit">Stop {r['stop']:.4g} · Objectif {r['objectif']:.4g}{'' if r['type'] in ('Forex', 'Matières premières') else f" · Quantité max {r['quantite']}"} · Risque {niveau_risque(r['vol_annuelle'])}</div>
  <details><summary>Pourquoi ?</summary>
    <h4>Technique</h4><ul>{''.join(f'<li>{html.escape(x)}</li>' for x in r['raisons_tech'])}</ul>
    <h4>Fondamentaux</h4><ul>{''.join(f'<li>{html.escape(x)}</li>' for x in r['raisons_fond'])}</ul>
    <h4>Actualités ({r['nb_news']}) · sentiment {r['sentiment']:+.2f}</h4>
    <p><b>Positives</b><br>{_liens(r['news_pos'])}</p><p><b>Négatives</b><br>{_liens(r['news_neg'])}</p>
    <h4>Dirigeants et décisions</h4><p>{html.escape(r['dirigeants']['texte'])}</p><p>{_liens(r['news_dirig'])}</p>
  </details>
</div>"""


def _carte_pepite(r, rang, titre_details="Pourquoi c'est une pépite ?"):
    etoiles = "★" * max(1, min(5, int(round((r['score_pepite'] + 1) * 2.5))))
    badges = ""
    if r.get("nouveau"):
        badges += '<span class="tag nouveau">🆕 Nouveau</span>'
    if r.get("fonds_acheteurs"):
        badges += f'<span class="tag fonds" title="Ouvert ou renforcé au dernier trimestre">🏦 Acheté par {html.escape(", ".join(r["fonds_acheteurs"][:2]))}</span>'
    lieu = " · ".join(x for x in (r.get("pays"), r.get("secteur") or r.get("theme")) if x) or r['type']
    cap = r.get("cap_usd")
    cap_txt = f" · capitalisation {cap / 1e9:,.0f} Md$".replace(",", " ") if cap else ""
    return f"""
<div class="carte" data-type="{html.escape(r['type'])}" data-zone="{html.escape(r.get('zone', ''))}">
  <div class="haut">
    <div><div class="nom">#{rang} {html.escape(r['nom'])}</div><div class="petit">{html.escape(r['ticker'])} · {html.escape(lieu)}</div></div>
    <div class="prix">{r['prix']:.2f} <small>{html.escape(r['devise'])}</small><br>{_spark_svg(r['spark'])}</div>
  </div>
  {('<div>' + badges + '</div>') if badges else ''}
  <div class="pep"><span class="etoiles">{etoiles}</span> score croissance {r['score_pepite']:+.2f} · risque <b>{niveau_risque(r['vol_annuelle'])}</b></div>
  <div class="petit">{_perf(r)}</div>
  <div class="signaux">
    <div><div class="petit">Court terme</div>{_badge(r['signal_ct'])}</div>
    <div><div class="petit">Long terme</div>{_badge(r['signal_lt'])}</div>
  </div>
  <details><summary>{html.escape(titre_details)}</summary>
    <ul>{''.join(f'<li>{html.escape(x)}</li>' for x in r['raisons_pepite'])}</ul>
    <h4>Bilan et valorisation</h4><ul>{''.join(f'<li>{html.escape(x)}</li>' for x in r['raisons_fond'])}</ul>
    <p><b>Actualités</b><br>{_liens(r['news_pos'] + r['news_neg'])}</p>
    <p><b>Dirigeants et décisions</b><br>{html.escape(r['dirigeants']['texte'])}<br>{_liens(r['news_dirig'])}</p>
    <p class="petit">Pire baisse sur 1 an : {r['max_dd_1an']:.0%} · volatilité {r['vol_annuelle']:.0%} par an{cap_txt}</p>
  </details>
</div>"""


def _section_fonds(fonds):
    if not fonds or not fonds.get("fonds"):
        return "<p class='petit'>Données des grands fonds indisponibles pour le moment.</p>"
    cartes = []
    for f in fonds["fonds"]:
        def liste(items, fmt):
            return "<ul>" + "".join(f"<li>{fmt(i)}</li>" for i in items) + "</ul>" if items else "<p class='petit'>—</p>"
        cartes.append(f"""
<div class="carte">
  <div class="nom">{html.escape(f['nom'])}</div>
  <div class="petit">Positions au {html.escape(f['trimestre'])} · publiées le {html.escape(f['publie'])}</div>
  <details open><summary>🆕 Nouvelles positions</summary>{liste(f['nouveaux'], lambda i: f"{html.escape(i['nom'])} <span class='petit'>({i['poids']:.1%} du fonds)</span>")}</details>
  <details><summary>⬆️ Renforcées</summary>{liste(f['renforces'], lambda i: f"{html.escape(i['nom'])} <b class='up'>{i['var']:+.0%}</b>")}</details>
  <details><summary>⬇️ Allégées</summary>{liste(f['alleges'], lambda i: f"{html.escape(i['nom'])} <b class='down'>{i['var']:+.0%}</b>")}</details>
  <details><summary>❌ Vendues entièrement</summary>{liste(f['vendus'], lambda i: html.escape(i['nom']))}</details>
  <details><summary>🏆 10 plus grosses positions</summary>{liste(f['top'], lambda i: f"{html.escape(i['nom'])} <span class='petit'>{i['poids']:.1%}</span>")}</details>
</div>""")
    return "".join(cartes)


def page_html(resultats, pepites, erreurs, auto_refresh_min=None, extra=None):
    cfg = charger_config()
    extra = extra or {}
    opps, etfs_m, marches, fonds = extra.get("opportunites", []), extra.get("etfs", []), extra.get("marches", []), extra.get("fonds")
    nb_pays = len({r.get("pays") for r in opps if r.get("pays")})
    nb_nouveaux = sum(1 for r in opps + pepites if r.get("nouveau"))
    maintenant = dt.datetime.now().strftime("%d/%m/%Y à %H:%M")
    tri = sorted(resultats, key=lambda x: -(x["score_ct"] + x["score_lt"]))
    nb_achat = sum(1 for r in resultats if r["score_lt"] >= 0.18)
    nb_prudence = sum(1 for r in resultats if r["score_ct"] <= -0.18)
    top_pep = pepites[0]["nom"] if pepites else "—"
    refresh = f'<meta http-equiv="refresh" content="{auto_refresh_min * 60}">' if auto_refresh_min else ""
    err = "".join(f"<li>{html.escape(e)}</li>" for e in erreurs)
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{refresh}
<title>SignalBourse</title>
<style>
:root{{--bg:#f6f7f9;--carte:#fff;--txt:#1d1d1f;--muted:#6b6f76;--bord:#e4e6ea;--accent:#0b57d0}}
@media (prefers-color-scheme: dark){{:root{{--bg:#121316;--carte:#1c1e22;--txt:#ececef;--muted:#9a9ea6;--bord:#2d3036;--accent:#7aa7ff}}}}
*{{box-sizing:border-box}} body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--txt)}}
header{{padding:18px 16px 8px;max-width:1200px;margin:auto}} h1{{margin:0;font-size:24px}}
.resume{{margin:6px 0 0;color:var(--muted)}} main{{max-width:1200px;margin:auto;padding:0 16px 40px}}
.onglets{{display:flex;gap:6px;margin:12px 0;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:3}}
.onglets button{{border:1px solid var(--bord);background:var(--carte);color:var(--txt);padding:8px 14px;border-radius:20px;font-size:14px;cursor:pointer}}
.onglets button.actif{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.filtres{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}} .filtres button{{font-size:12px;padding:5px 10px;border-radius:14px;border:1px solid var(--bord);background:transparent;color:var(--txt);cursor:pointer}}
.filtres button.actif{{background:var(--txt);color:var(--bg)}}
.grille{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
.carte{{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:8px}}
.haut{{display:flex;justify-content:space-between;gap:8px}} .nom{{font-weight:600}} .prix{{text-align:right;font-variant-numeric:tabular-nums}}
.petit{{font-size:12px;color:var(--muted)}} .signaux{{display:flex;gap:16px}}
.badge{{color:#fff;padding:3px 9px;border-radius:10px;font-size:12px;font-weight:600;display:inline-block;margin-top:2px}}
.up{{color:#0a7d32}} .down{{color:#c62828}} .pep{{font-size:13px}} .etoiles{{color:#e0a800;letter-spacing:1px}}
details summary{{cursor:pointer;color:var(--accent);font-size:14px}} details h4{{margin:10px 0 4px;font-size:13px}} details ul{{margin:4px 0;padding-left:18px;font-size:13px}}
details p{{font-size:13px}} a{{color:var(--accent);text-decoration:none}}
.avert{{background:#fff4e5;color:#5a3b00;padding:10px 12px;border-radius:10px;font-size:13px;margin:10px 0}}
@media (prefers-color-scheme: dark){{.avert{{background:#3a2c10;color:#ffdca3}}}}
.panneau{{display:none}} .panneau.actif{{display:block}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin-right:4px;font-weight:600}}
.nouveau{{background:#e8f0fe;color:#0b57d0}} .fonds{{background:#fdf1dc;color:#8a5a00}}
@media (prefers-color-scheme: dark){{.nouveau{{background:#1d2a44;color:#9cc0ff}} .fonds{{background:#3a2c10;color:#ffd38a}}}}
h3{{margin:18px 0 8px;font-size:17px}}
.methode{{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:14px;font-size:14px;line-height:1.5}}
</style></head><body>
<header>
  <h1>📈 SignalBourse</h1>
  <p class="resume">Mis à jour le {maintenant} · {len(resultats)} lignes suivies : <b>{nb_achat}</b> à acheter ou renforcer à long terme, <b>{nb_prudence}</b> à surveiller de près à court terme. Pépite n°1 du jour : <b>{html.escape(top_pep)}</b>.{f" Opportunités monde : <b>{len(opps)}</b> titres de {nb_pays} pays" + (f", dont <b>{nb_nouveaux}</b> nouveaux" if nb_nouveaux else "") + "." if opps else ""}</p>
</header>
<main>
  <div class="avert">Outil d'aide à la décision, <b>pas un conseil en investissement</b>. Aucun signal n'est garanti : tu peux perdre tout ou partie de ton capital. Les « pépites » sont plus risquées que les grandes valeurs ; limite chacune à 1–2 % de ton capital. Données Yahoo Finance (jusqu'à 15 min de retard).</div>
  <nav class="onglets">
    <button class="actif" data-onglet="liste">Ma liste</button>
    {'<button data-onglet="monde">🌍 Opportunités monde</button>' if opps or etfs_m else ''}
    <button data-onglet="pepites">💎 Pépites</button>
    {'<button data-onglet="marches">🛢️ Matières & Forex</button>' if marches else ''}
    {'<button data-onglet="fonds">🏦 Grands fonds</button>' if fonds else ''}
    <button data-onglet="methode">Méthode</button>
  </nav>

  <section class="panneau actif" id="liste">
    <div class="filtres" data-cible="g-liste">
      <button class="actif" data-f="tout">Tout</button><button data-f="Action">Actions</button><button data-f="ETF">ETF</button><button data-f="Obligations">Obligations</button>
    </div>
    <div class="grille" id="g-liste">{''.join(_carte_ligne(r) for r in tri)}</div>
  </section>

  <section class="panneau" id="monde">
    <p class="petit">Liste renouvelée automatiquement chaque jour : balayage des moyennes et grandes capitalisations de {len(__import__('monde').REGIONS)} pays (dont l'Afrique du Sud et l'Égypte), filtrées sur la croissance du chiffre d'affaires, puis classées selon la tendance, le bilan, la valorisation, l'avis des analystes et les achats des grands fonds. Le badge 🆕 signale une entrée dans la liste depuis moins de 7 jours.</p>
    <div class="filtres" data-cible="g-monde">
      <button class="actif" data-f="tout">Tout</button><button data-attr="zone" data-f="Amériques">Amériques</button><button data-attr="zone" data-f="Europe">Europe</button><button data-attr="zone" data-f="Asie-Pacifique">Asie-Pacifique</button><button data-attr="zone" data-f="Afrique &amp; Moyen-Orient">Afrique &amp; Moyen-Orient</button>
    </div>
    <div class="grille" id="g-monde">{''.join(_carte_pepite(r, i + 1, "Pourquoi cette opportunité ?") for i, r in enumerate(opps))}</div>
    {('<h3>📊 ETF les plus dynamiques du monde</h3><p class="petit">ETF de plus d’1 milliard d’encours, sans effet de levier. La plupart sont cotés aux États-Unis : ils ne sont pas éligibles au PEA, il faut un compte-titres.</p><div class="grille">' + ''.join(_carte_pepite(r, i + 1, "Pourquoi cet ETF ?") for i, r in enumerate(etfs_m)) + '</div>') if etfs_m else ''}
  </section>

  <section class="panneau" id="marches">
    <p class="petit">Signaux sur les matières premières (contrats à terme) et les devises. Ces marchés sont très volatils et souvent traités avec effet de levier : prudence.</p>
    <div class="filtres" data-cible="g-marches">
      <button class="actif" data-f="tout">Tout</button><button data-f="Matières premières">Matières premières</button><button data-f="Forex">Forex</button>
    </div>
    <div class="grille" id="g-marches">{''.join(_carte_ligne(r) for r in sorted(marches, key=lambda x: -(x["score_ct"] + x["score_lt"])))}</div>
  </section>

  <section class="panneau" id="fonds">
    <p class="petit">Ce que les plus grands investisseurs ont acheté et vendu au dernier trimestre, d'après leurs déclarations officielles à l'autorité boursière américaine (formulaire 13F). Ces positions sont publiées avec environ 45 jours de retard.</p>
    <div class="grille">{_section_fonds(fonds)}</div>
  </section>

  <section class="panneau" id="pepites">
    <p class="petit">Les {len(pepites)} meilleures pépites : petites et moyennes valeurs (dont celles détectées automatiquement dans le monde entier) et ETF thématiques. Elles combinent une forte croissance, un cours qui monte, une bonne qualité et du potentiel selon les analystes.</p>
    <div class="filtres" data-cible="g-pep">
      <button class="actif" data-f="tout">Tout</button><button data-f="Action">Actions</button><button data-f="ETF">ETF</button>
    </div>
    <div class="grille" id="g-pep">{''.join(_carte_pepite(r, i + 1) for i, r in enumerate(pepites))}</div>
  </section>

  <section class="panneau" id="methode"><div class="methode">
    <p><b>Court terme</b> (jours / semaines) : 70 % technique (moyennes 20/50 j, RSI, MACD, Bollinger, momentum), 25 % actualités des 14 derniers jours, 5 % achats et ventes des dirigeants.</p>
    <p><b>Long terme</b> (mois / années) : pour les actions, 40 % fondamentaux (PER, PEG, croissance, marges, dette, trésorerie, avis des analystes), 35 % tendance de fond (moyenne 200 j, momentum 12 mois), 15 % actualités, 10 % dirigeants. Pour les ETF et les obligations : 80 % tendance, 20 % actualités.</p>
    <p><b>Opportunités monde</b> : chaque jour, l'appli interroge le filtre de Yahoo Finance pour {len(__import__('monde').REGIONS)} pays (capitalisation d'environ 2 milliards de dollars ou plus, croissance du chiffre d'affaires supérieure à 5 %). Elle garde les 90 meilleurs sur la tendance, puis les analyse en détail (bilan, valorisation, analystes, actualités, dirigeants). Elle ajoute un bonus quand un grand fonds vient d'acheter le titre.</p>
    <p><b>Score croissance / pépite</b> : dynamique du cours sur 6 et 12 mois, tendance de fond, distance au plus haut, croissance du chiffre d'affaires et des bénéfices, rentabilité, potentiel selon les analystes, PEG, taille de l'entreprise.</p>
    <p><b>Gestion du risque</b> : stop = cours − 2 × ATR ; objectif = cours + 3 × ATR ; la quantité max limite la perte à {cfg['risque_par_trade_pct']} % du capital si le stop est touché.</p>
    <p><b>Conformité</b> : vérifie la politique de ton employeur sur les transactions personnelles, et n'utilise jamais une information non publique sur un client.</p>
    {'<p><b>Titres non trouvés</b> (vérifie le ticker sur finance.yahoo.com) :</p><ul>' + err + '</ul>' if erreurs else ''}
  </div></section>
</main>
<script>
document.querySelectorAll('.onglets button').forEach(b => b.onclick = () => {{
  document.querySelectorAll('.onglets button').forEach(x => x.classList.toggle('actif', x === b));
  document.querySelectorAll('.panneau').forEach(p => p.classList.toggle('actif', p.id === b.dataset.onglet));
  history.replaceState(null, '', '#' + b.dataset.onglet);
}});
if (location.hash) {{ const b = document.querySelector(`.onglets button[data-onglet="${{location.hash.slice(1)}}"]`); if (b) b.click(); }}
document.querySelectorAll('.filtres').forEach(f => f.querySelectorAll('button').forEach(b => b.onclick = () => {{
  f.querySelectorAll('button').forEach(x => x.classList.toggle('actif', x === b));
  document.querySelectorAll('#' + f.dataset.cible + ' .carte').forEach(c => {{
    const attr = b.dataset.attr || 'type';
    c.style.display = (b.dataset.f === 'tout' || c.dataset[attr] === b.dataset.f) ? '' : 'none';
  }});
}}));
</script>
</body></html>"""


def ecrire_page(resultats, pepites, erreurs, dossier=None, auto_refresh_min=None, extra=None):
    dossier = Path(dossier) if dossier else SORTIE
    dossier.mkdir(parents=True, exist_ok=True)
    page = page_html(resultats, pepites, erreurs, auto_refresh_min, extra)
    mdp = os.environ.get("SITE_PASSWORD")
    if mdp and dossier != SORTIE:
        import monde
        page = monde.chiffrer_page(page, mdp)
    chemin = dossier / "index.html"
    chemin.write_text(page, encoding="utf-8")
    if dossier == SORTIE:
        (SORTIE / f"rapport_{dt.datetime.now():%Y-%m-%d_%Hh%M}.html").write_text(page, encoding="utf-8")
    return chemin



def enregistrer_historique(resultats):
    lignes = [{k: r[k] for k in ("date", "ticker", "nom", "prix", "score_ct", "signal_ct", "score_lt", "signal_lt")}
              | {"horodatage": dt.datetime.now().isoformat(timespec="minutes")} for r in resultats]
    df = pd.DataFrame(lignes)
    df.to_csv(HISTO, mode="a", header=not HISTO.exists(), index=False, encoding="utf-8")


# ----------------------------------------------------------------------------
# Alertes
# ----------------------------------------------------------------------------

def envoyer_alerte(cfg, message):
    print("🔔 " + message)
    import os
    tok = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg["alertes"].get("telegram_bot_token")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or cfg["alertes"].get("telegram_chat_id")
    if tok and chat:
        try:
            data = urllib.parse.urlencode({"chat_id": chat, "text": message}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=10)
        except Exception as e:
            print(f"   (Telegram : échec de l'envoi : {e})")


# ----------------------------------------------------------------------------
# Commandes
# ----------------------------------------------------------------------------

def analyser_liste(liste, cfg, avec_news=True, silencieux=False):
    resultats, erreurs = [], []
    for e in liste:
        try:
            if not silencieux:
                print(f"Analyse de {e['ticker']}…", flush=True)
            resultats.append(analyser(e, cfg, avec_news))
        except Exception as ex:
            erreurs.append(f"{e['ticker']} : {ex}")
    return resultats, erreurs


def trouver_pepites(cfg, top=12, silencieux=False):
    """Analyse l'univers « pépites », garde les meilleures et ajoute leurs actualités."""
    res, err = analyser_liste(cfg.get("pepites", []), cfg, avec_news=False, silencieux=silencieux)
    res.sort(key=lambda r: -r["score_pepite"])
    meilleurs = res[:top]
    for r in meilleurs:
        try:
            an = analyser_actualites(actualites(r["ticker"], r["nom"]))
            r.update({"news_pos": an["positives"], "news_neg": an["negatives"], "news_dirig": an["dirigeants"],
                      "nb_news": an["nb"], "sentiment": round(an["score"], 3)})
        except Exception:
            pass
    return meilleurs, err


def tout_analyser(cfg, avec_news=True, avec_pepites=True, silencieux=False):
    resultats, erreurs = analyser_liste(cfg["watchlist"], cfg, avec_news, silencieux)
    pepites, err_p = trouver_pepites(cfg, silencieux=silencieux) if avec_pepites else ([], [])
    return resultats, pepites, erreurs + err_p


def afficher_console(resultats, pepites):
    print("\n{:<10} {:<28} {:>10}  {:<22} {:<22}".format("Ticker", "Nom", "Cours", "Court terme", "Long terme"))
    for r in sorted(resultats, key=lambda x: -(x["score_ct"] + x["score_lt"])):
        print("{:<10} {:<28} {:>10.2f}  {:<22} {:<22}".format(r["ticker"], r["nom"][:28], r["prix"], r["signal_ct"], r["signal_lt"]))
    if pepites:
        print("\n💎 Pépites du jour :")
        for i, r in enumerate(pepites, 1):
            print(f"  {i:>2}. {r['nom'][:30]:<30} {r['ticker']:<10} score {r['score_pepite']:+.2f}  risque {niveau_risque(r['vol_annuelle'])}")


def cmd_analyse(tickers=None, ouvrir=True):
    cfg = charger_config()
    if tickers:
        connus = {e["ticker"].upper(): e for e in cfg["watchlist"] + cfg.get("pepites", [])}
        liste = [connus.get(t.upper(), {"ticker": t.upper(), "nom": t.upper(), "type": "Action"}) for t in tickers]
        resultats, erreurs = analyser_liste(liste, cfg)
        pepites = []
    else:
        resultats, pepites, erreurs = tout_analyser(cfg)
    if not resultats and not pepites:
        print("Aucun résultat. " + " | ".join(erreurs))
        return
    chemin = ecrire_page(resultats, pepites, erreurs)
    enregistrer_historique(resultats + pepites)
    afficher_console(resultats, pepites)
    print(f"\nTableau de bord : {chemin}\n{AVERTISSEMENT}")
    if ouvrir:
        import webbrowser
        webbrowser.open(chemin.resolve().as_uri())


def cmd_pepites():
    cfg = charger_config()
    pepites, erreurs = trouver_pepites(cfg)
    afficher_console([], pepites)
    if erreurs:
        print("\nNon trouvés : " + " | ".join(erreurs))
    print(AVERTISSEMENT)


def _verifier_changements(cfg, resultats, precedent, envoyer=True):
    messages = []

    def signaler(m):
        messages.append(m)
        if envoyer:
            envoyer_alerte(cfg, m)
    for r in resultats:
        avant = precedent.get(r["ticker"], {})
        for horizon in ("ct", "lt"):
            cle = f"signal_{horizon}"
            if avant.get(cle) and avant[cle] != r[cle]:
                signaler(f"{r['nom']} : signal {'court' if horizon == 'ct' else 'long'} terme {avant[cle].lower()} → {r[cle].lower()} (cours {r['prix']:.2f})")
        if r["prix"] <= r["stop"] * 1.005 and avant.get("prix", 0) > r["stop"]:
            signaler(f"{r['nom']} approche de son seuil de protection ({r['stop']:.2f})")
        precedent[r["ticker"]] = {"signal_ct": r["signal_ct"], "signal_lt": r["signal_lt"], "prix": r["prix"]}
    ETAT.write_text(json.dumps(precedent, ensure_ascii=False), encoding="utf-8")
    return messages


def boucle_mise_a_jour(cfg, minutes, auto_refresh=True):
    precedent = json.loads(ETAT.read_text(encoding="utf-8")) if ETAT.exists() else {}
    pepites, tour = [], 0
    while True:
        try:
            cfg = charger_config()  # relit la config : tu peux ajouter des titres sans redémarrer
            complet = tour % 4 == 0  # actualités + pépites toutes les 4 passes
            resultats, erreurs = analyser_liste(cfg["watchlist"], cfg, avec_news=complet, silencieux=True)
            if complet:
                pepites, err_p = trouver_pepites(cfg, silencieux=True)
                erreurs += err_p
            ecrire_page(resultats, pepites, erreurs, auto_refresh_min=minutes if auto_refresh else None)
            _verifier_changements(cfg, resultats, precedent)
            print(f"[{dt.datetime.now():%H:%M}] tableau de bord mis à jour ({len(resultats)} lignes, {len(pepites)} pépites)", flush=True)
        except Exception as ex:
            print(f"[{dt.datetime.now():%H:%M}] erreur pendant la mise à jour : {ex}", flush=True)
        tour += 1
        time.sleep(minutes * 60)


def cmd_surveille():
    cfg = charger_config()
    minutes = cfg.get("intervalle_surveillance_minutes", 15)
    print(f"Surveillance en continu toutes les {minutes} min (Ctrl+C pour arrêter).")
    boucle_mise_a_jour(cfg, minutes)


def _ip_locale():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def cmd_app(port=8765):
    """L'appli : un tableau de bord dans ton navigateur, mis à jour en continu,
    accessible aussi depuis ton téléphone sur le même Wi-Fi."""
    import threading
    import webbrowser
    import http.server
    import functools
    cfg = charger_config()
    minutes = cfg.get("intervalle_surveillance_minutes", 15)
    SORTIE.mkdir(exist_ok=True)
    if not (SORTIE / "index.html").exists():
        (SORTIE / "index.html").write_text(
            '<!DOCTYPE html><meta charset="utf-8"><meta http-equiv="refresh" content="20">'
            '<body style="font-family:sans-serif;padding:40px">Première analyse en cours (1 à 3 minutes)… '
            'la page se recharge toute seule.</body>', encoding="utf-8")
    threading.Thread(target=boucle_mise_a_jour, args=(cfg, minutes), daemon=True).start()

    class Silencieux(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    gestionnaire = functools.partial(Silencieux, directory=str(SORTIE))
    serveur = http.server.ThreadingHTTPServer(("0.0.0.0", port), gestionnaire)
    url = f"http://localhost:{port}/"
    print(f"\nSignalBourse est ouvert : {url}")
    print(f"Sur ton téléphone (même Wi-Fi) : http://{_ip_locale()}:{port}/")
    print(f"Mise à jour toutes les {minutes} min. Laisse cette fenêtre ouverte ; Ctrl+C pour arrêter.\n")
    webbrowser.open(url)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("Arrêt.")


SELECTION = DOSSIER / "selection.json"
_CHAMPS_ENTREE = ("ticker", "nom", "type", "theme", "pays", "zone", "secteur", "recherche", "code_pays")


def _ajouter_news(liste):
    for r in liste:
        try:
            an = analyser_actualites(actualites(r["ticker"], r.get("recherche") or r["nom"]))
            r.update({"news_pos": an["positives"], "news_neg": an["negatives"], "news_dirig": an["dirigeants"],
                      "nb_news": an["nb"], "sentiment": round(an["score"], 3)})
            # le sentiment des actualités ajuste légèrement les scores
            r["score_ct"] = round(r["score_ct"] + 0.25 * an["score"], 3)
            r["signal_ct"] = libelle(r["score_ct"])
        except Exception:
            pass


def construire_monde(cfg, erreurs):
    """Opportunités monde (large caps), pépites (mid caps + liste perso), ETF mondiaux, matières & forex, grands fonds."""
    import monde
    aujourd_hui = dt.date.today().isoformat()
    univers = monde.univers_du_jour()
    fonds = monde.grands_fonds()
    sel = {}
    if SELECTION.exists():
        try:
            sel = json.loads(SELECTION.read_text(encoding="utf-8"))
        except Exception:
            sel = {}
    complet = sel.get("date") != aujourd_hui or not sel.get("opportunites") or "cryptos" not in sel
    if complet:
        cand_actions = univers.get("actions", [])[:90]
        cand_etfs = univers.get("etfs", [])
        cand_pep = cfg.get("pepites", [])
    else:
        cand_actions = sel.get("opportunites", []) + sel.get("pepites_auto", []) + sel.get("afrique", [])
        cand_etfs = sel.get("etfs", [])
        cand_pep = cfg.get("pepites", [])
    print(f"Mode {'complet (renouvellement de la liste)' if complet else 'rapide (mise à jour des cours)'} : "
          f"{len(cand_actions)} actions monde, {len(cand_etfs)} ETF, {len(cand_pep)} pépites perso", flush=True)

    res_actions, err = analyser_liste(cand_actions, cfg, avec_news=False, silencieux=True)
    erreurs += [e for e in err if not complet]  # en mode complet, on tait les tickers exotiques introuvables
    # on écarte les cotations secondaires (ex. Apple coté à Varsovie) et les doublons de catégories d'actions
    filtres, vus = [], set()
    for r in sorted(res_actions, key=lambda r: -(r["score_lt"] + r["score_pepite"])):
        attendu = monde.PAYS_YAHOO.get(r.get("code_pays", ""))
        siege = r.get("pays_siege")
        if attendu and siege and siege not in monde.TOLERANCE_SIEGE.get(attendu, {attendu}):
            continue
        cle = monde._norm(r["nom"])
        if cle in vus:
            continue
        vus.add(cle)
        filtres.append(r)
    grandes, moyennes = [], []
    for r in filtres:
        r["cap_usd"] = monde.en_dollars(r.get("capitalisation"), r.get("devise"))
        r["nouveau"] = monde.est_nouveau(univers, r["ticker"])
        r["fonds_acheteurs"] = monde.fonds_qui_achetent(r["nom"], fonds, r["ticker"])
        if r.get("pct_institutions"):
            r["raisons_pepite"] = r["raisons_pepite"] + [f"Détenu à {r['pct_institutions']:.0%} par des investisseurs institutionnels (fonds, assureurs, banques)"]
        bonus = 0.08 * min(len(r["fonds_acheteurs"]), 2)
        r["score_global"] = 0.45 * r["score_lt"] + 0.45 * r["score_pepite"] + 0.10 * r["score_ct"] + bonus
        if r["fonds_acheteurs"]:
            r["raisons_pepite"] = r["raisons_pepite"] + [f"Acheté ou renforcé au dernier trimestre par : {', '.join(r['fonds_acheteurs'])}"]
        (moyennes if (r["cap_usd"] or 0) and r["cap_usd"] < 10e9 else grandes).append(r)
    grandes.sort(key=lambda r: -r["score_global"])
    moyennes.sort(key=lambda r: -r["score_global"])
    def diversifier(liste, maxi, par_pays, par_pays_secteur):
        sortie, n_pays, n_ps = [], {}, {}
        for r in liste:
            if r["score_lt"] <= -0.1:
                continue
            p, ps = r.get("pays", ""), (r.get("pays", ""), r.get("secteur", ""))
            if n_pays.get(p, 0) >= par_pays or n_ps.get(ps, 0) >= par_pays_secteur:
                continue
            n_pays[p] = n_pays.get(p, 0) + 1
            n_ps[ps] = n_ps.get(ps, 0) + 1
            sortie.append(r)
            if len(sortie) >= maxi:
                break
        return sortie
    opportunites = diversifier(grandes, 30, 5, 2)
    pep_auto = diversifier(moyennes, 10, 2, 1)
    afrique = [r for r in sorted(filtres, key=lambda r: -r["score_global"]) if r.get("pays") in ("Afrique du Sud", "Égypte")][:6]

    res_pep, err = analyser_liste(cand_pep, cfg, avec_news=False, silencieux=True)
    erreurs += err
    for r in res_pep:
        r["fonds_acheteurs"] = monde.fonds_qui_achetent(r["nom"], fonds, r["ticker"])
    vus, pepites = set(), []
    for r in sorted(res_pep + pep_auto, key=lambda r: -(0.6 * r["score_pepite"] + 0.4 * r["score_lt"])):
        if r["ticker"] not in vus:
            vus.add(r["ticker"])
            pepites.append(r)
    pepites = pepites[:16]

    res_etf, err = analyser_liste(cand_etfs, cfg, avec_news=False, silencieux=True)
    for r in res_etf:
        r["nouveau"] = monde.est_nouveau(univers, r["ticker"])
    etfs = sorted(res_etf, key=lambda r: -(r["score_lt"] + r["score_pepite"]))[:12]

    marches, err = analyser_liste(monde.MATIERES + monde.FOREX, cfg, avec_news=True, silencieux=True)
    erreurs += err

    # --- cryptos : sélection renouvelée chaque jour parmi les 250 premières
    import crypto
    cand_crypto = crypto.selection() if complet else sel.get("cryptos", [])
    res_cr, _ = analyser_liste(cand_crypto, cfg, avec_news=False, silencieux=True)
    prelim = {c["ticker"]: c.get("score_prelim", 0) for c in cand_crypto}
    for r in res_cr:
        r["score_global"] = 0.5 * r["score_pepite"] + 0.3 * r["score_lt"] + 0.2 * prelim.get(r["ticker"], 0)
    base = [r for r in res_cr if r["ticker"] in ("BTC-USD", "ETH-USD")]
    autres = sorted([r for r in res_cr if r["ticker"] not in ("BTC-USD", "ETH-USD")], key=lambda r: -r["score_global"])[:14]
    cryptos = base + autres

    # badge « Nouveau » pour les cryptos (même registre que les actions)
    premiere = univers.setdefault("premiere_apparition", {})
    for r in cryptos:
        premiere.setdefault(r["ticker"], aujourd_hui)
        r["nouveau"] = monde.est_nouveau(univers, r["ticker"])
    try:
        monde.CACHE_UNIVERS.write_text(json.dumps(univers, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass

    _ajouter_news(opportunites + pepites + etfs + afrique + cryptos)

    if complet:
        garder = lambda lst: [{k: r.get(k, "") for k in _CHAMPS_ENTREE} for r in lst]
        SELECTION.write_text(json.dumps({"date": aujourd_hui, "opportunites": garder(opportunites),
                                         "pepites_auto": garder(pep_auto), "etfs": garder(etfs), "afrique": garder(afrique),
                                         "cryptos": [{k: r.get(k, "") for k in _CHAMPS_ENTREE} | {"score_prelim": prelim.get(r["ticker"], 0)} for r in cryptos]},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
    return {"opportunites": opportunites, "pepites": pepites, "etfs": etfs, "marches": marches, "afrique_actions": afrique,
            "cryptos": cryptos, "fonds": fonds, "complet": complet}


FICHES_CACHE = DOSSIER / "fiches_cache.json"


def donnees_fiche(ticker, cache):
    """Bilan sur plusieurs années et principaux investisseurs (actions seulement), mis en cache 7 jours."""
    c = cache.get(ticker)
    if c and (dt.date.today() - dt.date.fromisoformat(c["date"])).days < 7:
        return c
    out = {"date": dt.date.today().isoformat(), "bilan": [], "actionnaires": []}
    try:
        t = yf.Ticker(ticker)
        inc, cf = t.income_stmt, t.cashflow
        if inc is not None and not inc.empty:
            for col in list(inc.columns)[:4][::-1]:
                ligne = lambda df, nom: (float(df.loc[nom, col]) / 1e6 if df is not None and nom in df.index and col in df.columns
                                         and pd.notna(df.loc[nom, col]) else None)
                out["bilan"].append({"annee": str(col)[:4], "ca": ligne(inc, "Total Revenue"),
                                     "benefice": ligne(inc, "Net Income"), "fcf": ligne(cf, "Free Cash Flow")})
        h = t.institutional_holders
        if h is not None and not h.empty:
            col_part = next((c for c in h.columns if "pct" in c.lower() or "%" in c), None)
            for _, row in h.head(6).iterrows():
                out["actionnaires"].append({"nom": str(row.get("Holder", "")), "part": float(row[col_part]) if col_part else 0.0})
    except Exception:
        pass
    cache[ticker] = out
    return out


def actus_marche():
    news = []
    for q, hl, gl in (("bourse marchés actions", "fr", "FR"), ("stock market today", "en", "US")):
        try:
            news += _lire_rss(f"https://news.google.com/rss/search?q={urllib.parse.quote(q + ' when:1d')}&hl={hl}&gl={gl}&ceid={gl}:{hl}", 5)
        except Exception:
            pass
    return news[:8]


def vers_euros(montant, devise):
    import monde
    usd = monde.en_dollars(montant, devise or "EUR")
    eur = monde.en_dollars(1.0, "EUR")
    return usd / eur if usd and eur else None


def cmd_site():
    """Génère le site complet dans docs/ (version en ligne 24h/24 via GitHub Actions)."""
    import etat
    import interface
    import monde
    import portefeuille
    import calendrier
    import suivi
    import brvm
    etat.ouvrir()
    cfg = charger_config()
    resultats, erreurs = analyser_liste(cfg["watchlist"], cfg, avec_news=True)
    try:
        extra = construire_monde(cfg, erreurs)
    except Exception as ex:  # le module monde ne doit jamais bloquer le reste
        import traceback
        traceback.print_exc()
        print(f"Module monde indisponible : {ex}", flush=True)
        pep, err = trouver_pepites(cfg, silencieux=True)
        erreurs += err
        extra = {"pepites": pep, "complet": False}
    complet = extra.get("complet")
    pepites = extra.get("pepites", [])
    marches = extra.get("marches", [])

    # --- Portefeuille (secret PORTEFEUILLE)
    positions, _ = portefeuille.lire()
    connus = {r["ticker"]: r for r in resultats + pepites + marches + extra.get("opportunites", []) + extra.get("cryptos", [])
              + extra.get("etfs", []) + extra.get("afrique_actions", [])}
    a_analyser = [{"ticker": p["ticker"], "nom": p["ticker"], "type": p["type"] or ("Crypto" if p["ticker"].endswith("-USD") else "Action")}
                  for p in positions if p["ticker"] not in connus]
    res_pf, err = analyser_liste(a_analyser, cfg, avec_news=True, silencieux=True)
    erreurs += err
    for r in res_pf:
        try:
            nom_long = yf.Ticker(r["ticker"]).info.get("longName")
            if nom_long:
                r["nom"] = nom_long
        except Exception:
            pass
        connus[r["ticker"]] = r
    pf = portefeuille.construire(positions, connus, vers_euros) if positions else None

    # --- Afrique
    try:
        b = brvm.analyse()
    except Exception as ex:
        b = {"titres": [], "message": f"BRVM indisponible ({ex})"}
    afrique = {"brvm": b, "actions": extra.get("afrique_actions", []),
               "devises": [r for r in marches if r["ticker"] in ("USDZAR=X", "USDNGN=X", "EURMAD=X")]}

    # --- Calendrier
    titres_cal = [{"ticker": r["ticker"], "nom": r["nom"]} for r in
                  resultats + res_pf + extra.get("opportunites", [])[:15] + pepites[:8] if r["type"] == "Action"]
    if pf:
        titres_cal += [{"ticker": l["r"]["ticker"], "nom": l["r"]["nom"]} for l in pf["lignes"] if l["r"]["type"] == "Action"]
    vus = set()
    titres_cal = [t for t in titres_cal if not (t["ticker"] in vus or vus.add(t["ticker"]))]
    try:
        cal = calendrier.a_venir(titres_cal)
    except Exception as ex:
        print(f"Calendrier indisponible : {ex}", flush=True)
        cal = []

    # --- Alertes
    precedent = json.loads(ETAT.read_text(encoding="utf-8")) if ETAT.exists() else {}
    suivis = resultats + marches + ([l["r"] for l in pf["lignes"]] if pf else [])
    alertes = _verifier_changements(cfg, suivis, precedent, envoyer=True)
    mes_titres = {r["ticker"] for r in resultats} | ({l["r"]["ticker"] for l in pf["lignes"]} if pf else set())
    demain = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    proches = [e for e in cal if e["date"] <= demain and (e.get("ticker") in mes_titres or e["type"] == "Banque centrale")]
    alertes += [f"📅 {e['texte']} le {dt.date.fromisoformat(e['date']).strftime('%d/%m')}" for e in proches]
    if pf:
        alertes += [c for c in pf["conseils"] if "seuil de protection" in c or "« vendre »" in c or "« alléger »" in c]
    if complet and proches:
        envoyer_alerte(cfg, "📅 À venir : " + " ; ".join(e["texte"] for e in proches))

    # --- Bulletin de notes
    if complet or not HISTO.exists():
        tous_hist = resultats + pepites + marches + extra.get("opportunites", []) + extra.get("etfs", []) + extra.get("cryptos", []) + res_pf
        enregistrer_historique(tous_hist)
    try:
        bul = suivi.bulletin()
        simu = suivi.simulation(resultats + extra.get("opportunites", [])[:8], historique, backtest)
    except Exception as ex:
        print(f"Bulletin indisponible : {ex}", flush=True)
        bul, simu = {"jours": 0, "tableau": {}}, []

    data = {"liste": resultats, "portefeuille": pf, "opportunites": extra.get("opportunites", []), "etfs": extra.get("etfs", []),
            "pepites": pepites, "cryptos": extra.get("cryptos", []), "afrique": afrique, "marches": marches,
            "fonds": extra.get("fonds"), "calendrier": cal, "alertes": alertes, "bulletin": bul, "simulation": simu,
            "erreurs": erreurs, "actus_marche": actus_marche()}

    # --- Écriture du site
    sortie = DOSSIER / "docs"
    (sortie / "f").mkdir(parents=True, exist_ok=True)
    for vieux in (sortie / "f").glob("*.html"):
        vieux.unlink()
    mdp = os.environ.get("SITE_PASSWORD")
    proteger = (lambda h, pre="": monde.chiffrer_page(h, mdp, prefixe=pre)) if mdp else (lambda h, pre="": h)
    (sortie / "index.html").write_text(proteger(interface.page(data)), encoding="utf-8")

    cache_f = json.loads(FICHES_CACHE.read_text(encoding="utf-8")) if FICHES_CACHE.exists() else {}
    hist = pd.read_csv(HISTO) if HISTO.exists() else pd.DataFrame()
    tous = list(connus.values())
    for r in tous:
        ex = {"evenements": [e for e in cal if e.get("ticker") == r["ticker"]]}
        if r["type"] == "Action" and complet:
            ex.update(donnees_fiche(r["ticker"], cache_f))
        elif r["ticker"] in cache_f:
            ex.update({k: cache_f[r["ticker"]].get(k) for k in ("bilan", "actionnaires")})
        if not hist.empty:
            h = hist[hist["ticker"] == r["ticker"]].tail(40)
            ex["historique"] = [{"date": str(x["horodatage"])[:10], "prix": x["prix"], "signal_ct": x["signal_ct"], "signal_lt": x["signal_lt"]}
                                for _, x in h.iterrows()]
        (sortie / "f" / f"{interface.slug(r['ticker'])}.html").write_text(proteger(interface.fiche(r, ex), "../"), encoding="utf-8")
    FICHES_CACHE.write_text(json.dumps(cache_f, ensure_ascii=False), encoding="utf-8")
    (sortie / "manifest.json").write_text(json.dumps(interface.MANIFEST, ensure_ascii=False), encoding="utf-8")
    (sortie / "sw.js").write_text(interface.SERVICE_WORKER, encoding="utf-8")
    for t in (192, 512):
        if not (sortie / f"icone-{t}.png").exists():
            try:
                interface.icone(sortie / f"icone-{t}.png", t)
            except Exception as ex:
                print(f"Icône : {ex}", flush=True)
    (sortie / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Site généré : {sortie / 'index.html'} + {len(tous)} fiches", flush=True)
    resume = lambda lst, n=6: " | ".join(f"{r['nom'][:22]} ({r['signal_lt']}, pot {r['score_pepite']:+.2f})" for r in lst[:n])
    print("[résumé] opportunités :", len(data["opportunites"]), resume(data["opportunites"]), flush=True)
    print("[résumé] pépites :", len(pepites), resume(pepites), flush=True)
    print("[résumé] cryptos :", len(data["cryptos"]), resume(data["cryptos"], 8), flush=True)
    print("[résumé] afrique :", len(afrique["actions"]), resume(afrique["actions"]), "| BRVM :",
          "; ".join(f"{t['symbole']} {t['cours']} {t['variation_jour']:+.2%}" for t in b.get("titres", [])[:5]), flush=True)
    print("[résumé] calendrier :", len(cal), "; ".join(f"{e['date']} {e['texte'][:40]}" for e in cal[:5]), flush=True)
    print("[résumé] fonds :", len((extra.get("fonds") or {}).get("fonds", [])), "| portefeuille :", "oui" if pf else "non",
          "| bulletin :", bul.get("jours"), "jours | simulation :", len(simu), "| alertes :", len(alertes), flush=True)

    if complet and (os.environ.get("TELEGRAM_BOT_TOKEN") or cfg["alertes"].get("telegram_bot_token")):
        top = ", ".join(r["nom"] for r in (extra.get("opportunites") or [])[:3])
        pep = ", ".join(r["nom"] for r in pepites[:3])
        cr = ", ".join(r["nom"] for r in (extra.get("cryptos") or [])[2:5])
        envoyer_alerte(cfg, f"📈 SignalBourse : listes du jour renouvelées.\nOpportunités : {top}\nPépites : {pep}\nCryptos : {cr}")
    quelle = os.environ.get("NEWSLETTER", "").strip().lower()
    if quelle in ("lundi", "bilan"):
        import newsletter
        newsletter.envoyer(quelle, resultats, extra | {"portefeuille": pf, "calendrier": cal})
    etat.fermer()


def cmd_idees(top=15):
    cfg = charger_config()
    univers = [{"ticker": t, "nom": t, "type": "Action"} for t in cfg["univers_idees"]]
    res, _ = analyser_liste(univers, cfg, avec_news=False)
    res.sort(key=lambda r: -(r["score_ct"] + r["score_lt"]))
    print("\nMeilleures idées parmi les grandes valeurs (technique + fondamentaux) :")
    for r in res[:top]:
        print(f"  {r['ticker']:<10} CT {r['signal_ct']:<22} LT {r['signal_lt']:<22} cours {r['prix']:.2f}")
    print(AVERTISSEMENT)



def backtest(h, seuil_achat=0.18, seuil_vente=-0.18, frais=0.001):
    """Stratégie court terme : achète quand le score passe au-dessus du seuil, vend quand il passe sous le seuil de vente.
    Le signal du jour J est exécuté au cours du jour J+1 (pas de triche avec le futur)."""
    d = indicateurs(h)
    s = score_technique_ct(d)
    position = pd.Series(np.nan, index=d.index)
    position[s >= seuil_achat] = 1
    position[s <= seuil_vente] = 0
    position = position.ffill().fillna(0).shift(1).fillna(0)
    rdt = d["Close"].pct_change().fillna(0)
    changements = position.diff().abs().fillna(0)
    strat = position * rdt - changements * frais
    courbe = (1 + strat).cumprod()
    bh = (1 + rdt).cumprod()
    annees = max(len(d) / 252, 1e-9)

    def stats(c, r):
        return {"perf_totale": float(c.iloc[-1] - 1), "perf_annuelle": float(c.iloc[-1] ** (1 / annees) - 1),
                "pire_baisse": float((c / c.cummax() - 1).min()),
                "sharpe": float(r.mean() / r.std() * math.sqrt(252)) if r.std() > 0 else 0.0}

    # trades
    entrees = d.index[(position.diff() == 1)]
    sorties = d.index[(position.diff() == -1)]
    gains = []
    for e in entrees:
        s_ = sorties[sorties > e]
        fin = s_[0] if len(s_) else d.index[-1]
        gains.append(d["Close"].loc[fin] / d["Close"].loc[e] - 1)
    return {"strategie": stats(courbe, strat), "achat_conserve": stats(bh, rdt), "nb_trades": len(gains),
            "taux_reussite": float(np.mean([g > 0 for g in gains])) if gains else 0.0,
            "temps_investi": float(position.mean())}


def cmd_backtest(ticker):
    h = historique(ticker, "5y")
    r = backtest(h)
    s, b = r["strategie"], r["achat_conserve"]
    print(f"\nBacktest court terme {ticker} sur 5 ans (frais 0,1 % par ordre)")
    print(f"{'':<22}{'Stratégie':>12}{'Acheter et garder':>20}")
    print(f"{'Performance totale':<22}{s['perf_totale']:>12.1%}{b['perf_totale']:>20.1%}")
    print(f"{'Performance / an':<22}{s['perf_annuelle']:>12.1%}{b['perf_annuelle']:>20.1%}")
    print(f"{'Pire baisse':<22}{s['pire_baisse']:>12.1%}{b['pire_baisse']:>20.1%}")
    print(f"{'Ratio de Sharpe':<22}{s['sharpe']:>12.2f}{b['sharpe']:>20.2f}")
    print(f"Trades : {r['nb_trades']} · gagnants : {r['taux_reussite']:.0%} · temps investi : {r['temps_investi']:.0%}")
    print("Les performances passées ne préjugent pas des performances futures.")


def cmd_ajoute(ticker, nom=None, type_titre="Action"):
    cfg = charger_config()
    if any(e["ticker"].upper() == ticker.upper() for e in cfg["watchlist"]):
        print(f"{ticker} est déjà dans la watchlist.")
        return
    cfg["watchlist"].append({"ticker": ticker.upper(), "nom": nom or ticker.upper(), "type": type_titre})
    sauver_config(cfg)
    print(f"{ticker.upper()} ajouté.")


def cmd_retire(ticker):
    cfg = charger_config()
    avant = len(cfg["watchlist"])
    cfg["watchlist"] = [e for e in cfg["watchlist"] if e["ticker"].upper() != ticker.upper()]
    sauver_config(cfg)
    print(f"{ticker.upper()} retiré." if len(cfg["watchlist"]) < avant else f"{ticker} n'était pas dans la liste.")


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "aide"):
        print(__doc__)
        return
    c, args = argv[1], argv[2:]
    if c == "app":
        cmd_app(int(args[0]) if args else 8765)
    elif c == "analyse":
        cmd_analyse(args or None)
    elif c == "surveille":
        cmd_surveille()
    elif c == "pepites":
        cmd_pepites()
    elif c == "site":
        cmd_site()
    elif c == "newsletter" and args:
        os.environ["NEWSLETTER"] = args[0]
        cmd_site()
    elif c == "idees":
        cmd_idees()
    elif c == "backtest" and args:
        cmd_backtest(args[0])
    elif c == "ajoute" and args:
        cmd_ajoute(args[0], args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else "Action")
    elif c == "retire" and args:
        cmd_retire(args[0])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
