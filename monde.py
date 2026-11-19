# -*- coding: utf-8 -*-
"""
SignalBourse - module « Monde »
- Balayage automatique des actions mid et large caps de 50+ pays (dont Afrique du Sud et Égypte)
- ETF mondiaux les plus dynamiques
- Matières premières et forex
- Positions des grands fonds (déclarations 13F publiques de la SEC)
- Newsletters par e-mail
- Chiffrement de la page (mot de passe)
Tout est gratuit : Yahoo Finance (usage personnel) et SEC EDGAR.
"""

import base64
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import yfinance as yf
    from yfinance import EquityQuery, ETFQuery
except ImportError:  # pragma: no cover
    yf = None

DOSSIER = Path(__file__).resolve().parent
CACHE_UNIVERS = DOSSIER / "univers_auto.json"
CACHE_FONDS = DOSSIER / "fonds_13f.json"

# Régions balayées, avec un seuil de capitalisation (≈ 2 milliards de dollars) exprimé en monnaie locale.
REGIONS = {
    "us": ("États-Unis", "Amériques", 2e9), "ca": ("Canada", "Amériques", 2.8e9), "br": ("Brésil", "Amériques", 11e9),
    "mx": ("Mexique", "Amériques", 35e9),
    "fr": ("France", "Europe", 1.8e9), "de": ("Allemagne", "Europe", 1.8e9), "nl": ("Pays-Bas", "Europe", 1.8e9),
    "it": ("Italie", "Europe", 1.8e9), "es": ("Espagne", "Europe", 1.8e9), "be": ("Belgique", "Europe", 1.8e9),
    "ch": ("Suisse", "Europe", 1.7e9), "gb": ("Royaume-Uni", "Europe", 1.6e9), "se": ("Suède", "Europe", 20e9),
    "dk": ("Danemark", "Europe", 13e9), "no": ("Norvège", "Europe", 21e9), "fi": ("Finlande", "Europe", 1.8e9),
    "pl": ("Pologne", "Europe", 8e9),
    "jp": ("Japon", "Asie-Pacifique", 300e9), "kr": ("Corée du Sud", "Asie-Pacifique", 2.8e12),
    "tw": ("Taïwan", "Asie-Pacifique", 65e9), "hk": ("Hong Kong", "Asie-Pacifique", 16e9),
    "in": ("Inde", "Asie-Pacifique", 170e9), "sg": ("Singapour", "Asie-Pacifique", 2.7e9),
    "au": ("Australie", "Asie-Pacifique", 3e9), "id": ("Indonésie", "Asie-Pacifique", 32e12),
    "za": ("Afrique du Sud", "Afrique & Moyen-Orient", 37e9), "eg": ("Égypte", "Afrique & Moyen-Orient", 95e9),
    "sa": ("Arabie saoudite", "Afrique & Moyen-Orient", 7.5e9), "ae": ("Émirats arabes unis", "Afrique & Moyen-Orient", 7.3e9),
    "il": ("Israël", "Afrique & Moyen-Orient", 7e9),
}

PAYS_YAHOO = {
    "us": "United States", "ca": "Canada", "br": "Brazil", "mx": "Mexico", "fr": "France", "de": "Germany",
    "nl": "Netherlands", "it": "Italy", "es": "Spain", "be": "Belgium", "ch": "Switzerland", "gb": "United Kingdom",
    "se": "Sweden", "dk": "Denmark", "no": "Norway", "fi": "Finland", "pl": "Poland", "jp": "Japan", "kr": "South Korea",
    "tw": "Taiwan", "hk": "Hong Kong", "in": "India", "sg": "Singapore", "au": "Australia", "id": "Indonesia",
    "za": "South Africa", "eg": "Egypt", "sa": "Saudi Arabia", "ae": "United Arab Emirates", "il": "Israel",
}
# Pays dont le siège est accepté même s'il diffère du pays de cotation (sociétés cotées hors de leur pays d'origine)
TOLERANCE_SIEGE = {"Hong Kong": {"China", "Hong Kong", "Macau"}, "Netherlands": {"Netherlands", "Luxembourg"},
                   "United Kingdom": {"United Kingdom", "Jersey", "Guernsey", "Isle of Man", "Ireland"},
                   "Norway": {"Norway", "Bermuda", "Marshall Islands", "Cyprus"}, "Singapore": {"Singapore"}}

MATIERES = [
    {"ticker": "GC=F", "nom": "Or", "type": "Matières premières", "recherche": "gold price"},
    {"ticker": "SI=F", "nom": "Argent (métal)", "type": "Matières premières", "recherche": "silver price"},
    {"ticker": "PL=F", "nom": "Platine", "type": "Matières premières", "recherche": "platinum price"},
    {"ticker": "HG=F", "nom": "Cuivre", "type": "Matières premières", "recherche": "copper price"},
    {"ticker": "BZ=F", "nom": "Pétrole Brent", "type": "Matières premières", "recherche": "Brent oil price"},
    {"ticker": "CL=F", "nom": "Pétrole WTI", "type": "Matières premières", "recherche": "WTI crude oil"},
    {"ticker": "NG=F", "nom": "Gaz naturel", "type": "Matières premières", "recherche": "natural gas price"},
    {"ticker": "ZW=F", "nom": "Blé", "type": "Matières premières", "recherche": "wheat prices"},
    {"ticker": "ZC=F", "nom": "Maïs", "type": "Matières premières", "recherche": "corn prices"},
    {"ticker": "KC=F", "nom": "Café", "type": "Matières premières", "recherche": "coffee prices"},
    {"ticker": "CC=F", "nom": "Cacao", "type": "Matières premières", "recherche": "cocoa prices"},
    {"ticker": "SB=F", "nom": "Sucre", "type": "Matières premières", "recherche": "sugar prices"},
]
FOREX = [
    {"ticker": "EURUSD=X", "nom": "Euro / Dollar (EUR/USD)", "type": "Forex", "recherche": "EUR/USD euro dollar"},
    {"ticker": "USDJPY=X", "nom": "Dollar / Yen (USD/JPY)", "type": "Forex", "recherche": "USD/JPY yen"},
    {"ticker": "GBPUSD=X", "nom": "Livre / Dollar (GBP/USD)", "type": "Forex", "recherche": "GBP/USD sterling"},
    {"ticker": "USDCHF=X", "nom": "Dollar / Franc suisse (USD/CHF)", "type": "Forex", "recherche": "USD/CHF franc"},
    {"ticker": "EURGBP=X", "nom": "Euro / Livre (EUR/GBP)", "type": "Forex", "recherche": "EUR/GBP"},
    {"ticker": "EURCHF=X", "nom": "Euro / Franc suisse (EUR/CHF)", "type": "Forex", "recherche": "EUR/CHF"},
    {"ticker": "AUDUSD=X", "nom": "Dollar australien / Dollar (AUD/USD)", "type": "Forex", "recherche": "AUD/USD"},
    {"ticker": "USDCAD=X", "nom": "Dollar / Dollar canadien (USD/CAD)", "type": "Forex", "recherche": "USD/CAD loonie"},
    {"ticker": "USDCNY=X", "nom": "Dollar / Yuan (USD/CNY)", "type": "Forex", "recherche": "yuan dollar"},
    {"ticker": "USDZAR=X", "nom": "Dollar / Rand sud-africain (USD/ZAR)", "type": "Forex", "recherche": "rand dollar"},
    {"ticker": "USDNGN=X", "nom": "Dollar / Naira nigérian (USD/NGN)", "type": "Forex", "recherche": "naira dollar"},
    {"ticker": "EURMAD=X", "nom": "Euro / Dirham marocain (EUR/MAD)", "type": "Forex", "recherche": "dirham euro"},
    {"ticker": "BTC-USD", "nom": "Bitcoin / Dollar (très risqué)", "type": "Forex", "recherche": "bitcoin price"},
]

# Grands investisseurs qui publient leurs positions (formulaire 13F, avec ~45 jours de retard)
FONDS = {
    "Berkshire Hathaway (Warren Buffett)": "0001067983",
    "Pershing Square (Bill Ackman)": "0001336528",
    "Appaloosa (David Tepper)": "0001656456",
    "Duquesne Family Office (Stanley Druckenmiller)": "0001536411",
    "Scion Asset Management (Michael Burry)": "0001649339",
    "Bridgewater Associates (Ray Dalio)": "0001350694",
    "Tiger Global Management": "0001167483",
    "Coatue Management": "0001135730",
    "Fundsmith (Terry Smith)": "0001569205",
    "Baillie Gifford": "0001088875",
}
UA_SEC_LISTE = [
    os.environ.get("SEC_USER_AGENT") or "Ismael Kouloumba holdingismael@users.noreply.github.com",
    "SignalBourse/1.0 (personal research; holdingismael@users.noreply.github.com)",
]


def log(msg):
    print(f"[monde] {msg}", flush=True)


# ----------------------------------------------------------------------------
# Taux de change (pour comparer les capitalisations en dollars)
# ----------------------------------------------------------------------------

_FX = {"USD": 1.0}


def en_dollars(montant, devise):
    if not montant or not devise:
        return None
    div = 1.0
    if devise in ("GBp", "GBX"):
        devise, div = "GBP", 100.0
    elif devise == "ZAc":
        devise, div = "ZAR", 100.0
    elif devise == "ILA":
        devise, div = "ILS", 100.0
    devise = devise.upper()
    if devise not in _FX:
        try:
            h = yf.Ticker(f"{devise}USD=X").history(period="5d")
            _FX[devise] = float(h["Close"].iloc[-1]) if not h.empty else None
        except Exception:
            _FX[devise] = None
    taux = _FX.get(devise)
    return montant / div * taux if taux else None


# ----------------------------------------------------------------------------
# Balayage mondial
# ----------------------------------------------------------------------------

def _screen(filtres, taille, tri, asc=False):
    try:
        r = yf.screen(EquityQuery("and", filtres), size=taille, sortField=tri, sortAsc=asc)
        return r.get("quotes", []) if isinstance(r, dict) else []
    except Exception as ex:
        log(f"filtre : {ex}")
        return []


def _requete_region(code, seuil, taille=40):
    region = EquityQuery("eq", ["region", code])
    croissance = EquityQuery("gt", ["totalrevenues1yrgrowth.lasttwelvemonths", 5])
    # grandes capitalisations en croissance
    grandes = _screen([region, EquityQuery("gte", ["intradaymarketcap", seuil * 5]), croissance], taille, "intradaymarketcap")
    # moyennes capitalisations, triées par croissance du chiffre d'affaires
    moyennes = _screen([region, EquityQuery("btwn", ["intradaymarketcap", seuil, seuil * 5]), croissance],
                       max(15, taille // 2), "totalrevenues1yrgrowth.lasttwelvemonths")
    quotes = grandes + moyennes
    if not quotes:  # repli 1 : sans filtre de croissance (bilans manquants dans certains pays)
        quotes = _screen([region, EquityQuery("gte", ["intradaymarketcap", seuil])], taille, "intradaymarketcap")
    if not quotes:  # repli 2 : les plus grosses capitalisations du pays, sans seuil
        quotes = _screen([region], 20, "intradaymarketcap")
    return quotes


def _score_rapide(c):
    """Pré-sélection sur les cours : tendance de fond et dynamique 3 / 6 / 12 mois."""
    c = c.dropna()
    if len(c) < 200:
        return None
    sma200 = c.rolling(200).mean().iloc[-1]
    s = 0.0
    s += 0.3 if c.iloc[-1] > sma200 else -0.3
    for n, w in ((63, 0.8), (126, 0.6), (250, 0.4)):
        if len(c) > n:
            s += float(np.clip(c.iloc[-1] / c.iloc[-n] - 1, -0.6, 0.8)) * w
    s -= max(0.0, float(c.pct_change().std() * np.sqrt(252)) - 0.45)  # pénalise l'excès de volatilité
    return s


def balayer_monde(par_region=40, garder=110):
    """Retourne la liste des candidats (tickers) issus du balayage mondial, triés par score rapide."""
    candidats = {}
    for code, (pays, zone, seuil) in REGIONS.items():
        quotes = _requete_region(code, seuil, 100 if code == "us" else par_region)
        for q in quotes:
            sym = q.get("symbol")
            if not sym or q.get("quoteType", "EQUITY") != "EQUITY":
                continue
            if re.search(r"3[2-59]\.SA$", sym):  # certificats brésiliens (BDR) d'actions étrangères
                continue
            candidats[sym] = {"ticker": sym, "nom": q.get("longName") or q.get("shortName") or sym, "type": "Action",
                              "pays": pays, "zone": zone, "secteur": q.get("sector", ""), "code_pays": code}
        log(f"{pays} : {len(quotes)} titres")
        time.sleep(0.4)
    log(f"{len(candidats)} candidats au total")
    if not candidats:
        return []
    tickers = list(candidats)
    scores = {}
    for i in range(0, len(tickers), 80):
        lot = tickers[i:i + 80]
        try:
            df = yf.download(lot, period="14mo", interval="1d", auto_adjust=True, progress=False, group_by="ticker", threads=True)
        except Exception as ex:
            log(f"téléchargement lot {i} : {ex}")
            continue
        for t in lot:
            try:
                c = df[t]["Close"] if len(lot) > 1 else df["Close"]
                s = _score_rapide(c)
                if s is not None:
                    scores[t] = s
            except Exception:
                pass
    tri = sorted(scores, key=lambda t: -scores[t])[:garder]
    return [candidats[t] | {"score_rapide": round(scores[t], 3)} for t in tri]


_MOTS_ETF = r"\b(ISHARES|XTRACKERS|SPDR|STATE STREET|INVESCO|VANGUARD|AMUNDI|LYXOR|WISDOMTREE|GLOBAL X|VANECK|UCITS|ETF|FUND|USD|EUR|GBP|CHF|ACC|DIST|INC|1C|1D|2C|C|D|THE|SELECT|SECTOR|INDEX|TRUST|SHARES|CLASS|S P|MSCI)\b"


def _cle_etf(nom):
    import unicodedata
    n = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().upper()
    n = re.sub(r"[^A-Z0-9 ]", " ", n.replace("&", " "))
    n = re.sub(_MOTS_ETF, " ", n)
    return " ".join(n.split()[:2])


def etf_monde(garder=30):
    """ETF les plus dynamiques (encours > 1 milliard), sans doublons de cotation ni effet de levier, 2 par thème max."""
    try:
        q = ETFQuery("gt", ["fundnetassets", 1e9])
        r = yf.screen(q, size=250, sortField="trailing_3m_return", sortAsc=False)
        quotes = r.get("quotes", []) if isinstance(r, dict) else []
    except Exception as ex:
        log(f"ETF : échec du filtre ({ex})")
        quotes = []
    vus_nom, themes, sortie = set(), {}, []
    for q in quotes:
        sym = q.get("symbol", "")
        nom = q.get("longName") or q.get("shortName") or sym
        if re.search(r"\b(2X|3X|ULTRA|LEVERAGED|BULL|BEAR|INVERSE|SHORT|DAILY)\b", nom.upper()):
            continue
        if sym.endswith((".MX", ".SA", ".BA", ".SN", ".LM")):  # cotations secondaires en Amérique latine
            continue
        nom_court = re.sub(r"\s+", " ", re.sub(r"\(.*?\)|\b(Acc|Dist|1C|1D|USD|EUR)\b", "", nom)).strip().lower()
        if nom_court in vus_nom:
            continue
        theme = _cle_etf(nom)
        if themes.get(theme, 0) >= 2:
            continue
        vus_nom.add(nom_court)
        themes[theme] = themes.get(theme, 0) + 1
        sortie.append({"ticker": sym, "nom": nom, "type": "ETF", "pays": "Monde", "zone": "ETF", "secteur": ""})
        if len(sortie) >= garder:
            break
    log(f"{len(sortie)} ETF retenus")
    return sortie


def univers_du_jour(forcer=False):
    """Univers renouvelé une fois par jour (cache), avec date de première apparition pour le badge « Nouveau »."""
    aujourd_hui = dt.date.today().isoformat()
    cache = {}
    if CACHE_UNIVERS.exists():
        try:
            cache = json.loads(CACHE_UNIVERS.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    if cache.get("date") == aujourd_hui and not forcer and cache.get("actions"):
        return cache
    actions = balayer_monde()
    etfs = etf_monde()
    if not actions:  # en cas de panne de la source, on garde l'univers de la veille
        log("balayage vide : univers précédent conservé")
        return cache
    premiere = cache.get("premiere_apparition", {})
    for e in actions + etfs:
        premiere.setdefault(e["ticker"], aujourd_hui)
    cache = {"date": aujourd_hui, "actions": actions, "etfs": etfs, "premiere_apparition": premiere}
    CACHE_UNIVERS.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def est_nouveau(cache, ticker, jours=7):
    d = cache.get("premiere_apparition", {}).get(ticker)
    if not d:
        return False
    try:
        return (dt.date.today() - dt.date.fromisoformat(d)).days < jours and d != min(cache["premiere_apparition"].values())
    except Exception:
        return False


# ----------------------------------------------------------------------------
# Grands fonds (13F SEC)
# ----------------------------------------------------------------------------

def _get(url):
    derniere = None
    for ua in UA_SEC_LISTE:
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json, text/xml, */*",
                                                   "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError as ex:
            derniere = ex
            corps = ex.read()[:200].decode("utf-8", "ignore") if hasattr(ex, "read") else ""
            log(f"SEC {ex.code} avec l'agent « {ua[:30]}… » : {corps.strip()[:120]}")
            time.sleep(1)
    raise derniere


def _positions_13f(cik, accession):
    acc = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/"
    index = json.loads(_get(base + "index.json"))
    fichiers = [f["name"] for f in index["directory"]["item"]]
    xmls = [f for f in fichiers if f.lower().endswith(".xml") and "primary_doc" not in f.lower()]
    if not xmls:
        return {}
    racine = ET.fromstring(_get(base + xmls[0]))
    pos = {}
    for info in racine.iter():
        if not info.tag.endswith("infoTable"):
            continue
        d = {c.tag.split("}")[-1]: c for c in info.iter()}
        nom = (d.get("nameOfIssuer").text or "").strip() if d.get("nameOfIssuer") is not None else ""
        cusip = (d.get("cusip").text or "").strip() if d.get("cusip") is not None else nom
        try:
            valeur = float(d["value"].text)
            parts = float(d["sshPrnamt"].text)
        except Exception:
            continue
        if d.get("putCall") is not None:  # options : ignorées
            continue
        p = pos.setdefault(cusip, {"nom": nom, "valeur": 0.0, "parts": 0.0})
        p["valeur"] += valeur
        p["parts"] += parts
    return pos


def grands_fonds(forcer=False):
    """Dernières positions et mouvements des grands fonds. Mis en cache 7 jours (les 13F sont trimestriels)."""
    if CACHE_FONDS.exists() and not forcer:
        try:
            cache = json.loads(CACHE_FONDS.read_text(encoding="utf-8"))
            if (dt.date.today() - dt.date.fromisoformat(cache["date"])).days < 7:
                return cache
        except Exception:
            pass
    sortie = {"date": dt.date.today().isoformat(), "fonds": []}
    for nom_fonds, cik in FONDS.items():
        try:
            sub = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            r = sub["filings"]["recent"]
            dep = [(r["accessionNumber"][i], r["reportDate"][i], r["filingDate"][i])
                   for i, f in enumerate(r["form"]) if f == "13F-HR"]
            if len(dep) < 1:
                continue
            actuel = _positions_13f(cik, dep[0][0])
            time.sleep(0.3)
            avant = _positions_13f(cik, dep[1][0]) if len(dep) > 1 else {}
            total = sum(p["valeur"] for p in actuel.values()) or 1
            top = sorted(actuel.values(), key=lambda p: -p["valeur"])[:10]
            nouveaux = [actuel[c] for c in actuel if c not in avant]
            nouveaux = sorted(nouveaux, key=lambda p: -p["valeur"])[:8]
            renforces, alleges = [], []
            for c, p in actuel.items():
                if c in avant and avant[c]["parts"] > 0:
                    var = p["parts"] / avant[c]["parts"] - 1
                    if var > 0.15:
                        renforces.append(p | {"var": var})
                    elif var < -0.15:
                        alleges.append(p | {"var": var})
            vendus = sorted([avant[c] for c in avant if c not in actuel], key=lambda p: -p["valeur"])[:8]
            sortie["fonds"].append({
                "nom": nom_fonds, "trimestre": dep[0][1], "publie": dep[0][2],
                "top": [{"nom": p["nom"], "poids": p["valeur"] / total} for p in top],
                "nouveaux": [{"nom": p["nom"], "poids": p["valeur"] / total} for p in nouveaux],
                "renforces": [{"nom": p["nom"], "var": p["var"]} for p in sorted(renforces, key=lambda p: -p["valeur"])[:8]],
                "alleges": [{"nom": p["nom"], "var": p["var"]} for p in sorted(alleges, key=lambda p: -p["valeur"])[:8]],
                "vendus": [{"nom": p["nom"]} for p in vendus],
            })
            log(f"13F {nom_fonds} : {len(actuel)} lignes ({dep[0][1]})")
            time.sleep(0.3)
        except Exception as ex:
            log(f"13F {nom_fonds} : {ex}")
            if "403" in str(ex) and not sortie["fonds"]:
                log("accès SEC refusé depuis ce serveur : section « Grands fonds » reportée")
                break
    if sortie["fonds"]:
        CACHE_FONDS.write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    elif CACHE_FONDS.exists():
        return json.loads(CACHE_FONDS.read_text(encoding="utf-8"))
    return sortie


_SUFFIXES = r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|SA|NV|AG|SE|HOLDINGS?|GROUP|CLASS [A-C]|CL [A-C]|COM|NEW|THE|DEL|SPONSORED ADR|ADR|N V|S A)\b"


def _norm(nom):
    import unicodedata
    n = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode()
    n = re.sub(r"[^A-Z0-9 ]", " ", n.upper())
    n = re.sub(_SUFFIXES, " ", n)
    return " ".join(n.split())


def fonds_qui_achetent(nom_titre, fonds):
    """Noms des fonds qui ont ouvert ou renforcé une position sur ce titre au dernier trimestre."""
    cle = _norm(nom_titre)
    if len(cle) < 3:
        return []
    mots = cle.split()[:2]
    cle2 = " ".join(mots)
    acheteurs = []
    for f in fonds.get("fonds", []):
        for p in f["nouveaux"] + f["renforces"]:
            pn = _norm(p["nom"])
            if pn and (pn.startswith(cle2) or cle2.startswith(pn)):
                acheteurs.append(f["nom"].split(" (")[0])
                break
    return acheteurs


# ----------------------------------------------------------------------------
# Newsletters par e-mail (Gmail ou tout serveur SMTP, gratuit)
# ----------------------------------------------------------------------------

def envoyer_email(sujet, html_corps):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    hote = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user, mdp, dest = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD"), os.environ.get("EMAIL_TO")
    if not (user and mdp and dest):
        log("e-mail non configuré (secrets SMTP_USER, SMTP_PASSWORD, EMAIL_TO) : newsletter enregistrée seulement")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = sujet, f"SignalBourse <{user}>", dest
    msg.attach(MIMEText(html_corps, "html", "utf-8"))
    with smtplib.SMTP(hote, port, timeout=30) as s:
        s.starttls()
        s.login(user, mdp)
        s.sendmail(user, [d.strip() for d in dest.split(",")], msg.as_string())
    log(f"newsletter envoyée à {dest}")
    return True


# ----------------------------------------------------------------------------
# Chiffrement de la page (seul quelqu'un qui a le mot de passe peut la lire)
# ----------------------------------------------------------------------------

def chiffrer_page(page_html, mot_de_passe, iterations=250000):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    sel, iv = os.urandom(16), os.urandom(12)
    cle = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=iterations).derive(mot_de_passe.encode())
    chiffre = AESGCM(cle).encrypt(iv, page_html.encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode()
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>SignalBourse</title>
<meta name="robots" content="noindex,nofollow">
<style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#eee;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.b{{background:#1b1e24;padding:28px;border-radius:14px;width:min(360px,90vw);text-align:center}}
input{{width:100%;padding:12px;border-radius:8px;border:1px solid #333;background:#0f1115;color:#eee;font-size:16px;margin:12px 0}}
button{{width:100%;padding:12px;border:0;border-radius:8px;background:#3b82f6;color:#fff;font-size:16px;cursor:pointer}}
label{{font-size:13px;color:#aaa;display:flex;gap:6px;align-items:center;justify-content:center;margin-top:10px}} #e{{color:#f87171;font-size:14px;min-height:18px}}</style></head>
<body><form class="b" id="f"><h2>📈 SignalBourse</h2><p>Accès privé</p>
<input id="p" type="password" placeholder="Mot de passe" autocomplete="current-password" autofocus>
<button>Ouvrir</button><label><input id="r" type="checkbox" style="width:auto;margin:0"> Se souvenir sur cet appareil</label><div id="e"></div></form>
<script>
const D={{s:"{b(sel)}",i:"{b(iv)}",c:"{b(chiffre)}",n:{iterations}}};
const u=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function ouvrir(mdp){{
  const k0=await crypto.subtle.importKey('raw',new TextEncoder().encode(mdp),'PBKDF2',false,['deriveKey']);
  const k=await crypto.subtle.deriveKey({{name:'PBKDF2',salt:u(D.s),iterations:D.n,hash:'SHA-256'}},k0,{{name:'AES-GCM',length:256}},false,['decrypt']);
  const t=await crypto.subtle.decrypt({{name:'AES-GCM',iv:u(D.i)}},k,u(D.c));
  const h=new TextDecoder().decode(t); document.open(); document.write(h); document.close();
}}
let m=null; try{{m=localStorage.getItem('sb_mdp')}}catch(e){{}}
if(m) ouvrir(m).catch(()=>{{try{{localStorage.removeItem('sb_mdp')}}catch(e){{}}}});
document.getElementById('f').onsubmit=async ev=>{{ev.preventDefault();const p=document.getElementById('p').value;
  const garder=document.getElementById('r').checked;
  try{{await ouvrir(p); if(garder){{try{{localStorage.setItem('sb_mdp',p)}}catch(e){{}}}}}}
  catch(e){{document.getElementById('e').textContent='Mot de passe incorrect';}}}};
</script></body></html>"""
