# -*- coding: utf-8 -*-
"""Calendrier : résultats d'entreprises, dividendes, décisions de la Fed et de la BCE."""

import datetime as dt
import json
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
CACHE = DOSSIER / "calendrier_cache.json"

# Dates officielles (jour de l'annonce de la décision)
BANQUES_CENTRALES = [
    ("2026-12-09", "Fed (États-Unis)", "Décision sur les taux d'intérêt américains"),
    ("2026-12-17", "BCE (zone euro)", "Décision sur les taux d'intérêt de la zone euro"),
    ("2027-01-27", "Fed (États-Unis)", "Décision sur les taux d'intérêt américains"),
    ("2027-02-04", "BCE (zone euro)", "Décision sur les taux d'intérêt de la zone euro"),
    ("2027-03-17", "Fed (États-Unis)", "Décision sur les taux, avec nouvelles prévisions économiques"),
    ("2027-03-18", "BCE (zone euro)", "Décision sur les taux, avec nouvelles prévisions économiques"),
    ("2027-04-28", "Fed (États-Unis)", "Décision sur les taux d'intérêt américains"),
    ("2027-04-29", "BCE (zone euro)", "Décision sur les taux d'intérêt de la zone euro"),
    ("2027-06-09", "Fed (États-Unis)", "Décision sur les taux, avec nouvelles prévisions économiques"),
    ("2027-07-28", "Fed (États-Unis)", "Décision sur les taux d'intérêt américains"),
    ("2027-09-15", "Fed (États-Unis)", "Décision sur les taux, avec nouvelles prévisions économiques"),
    ("2027-12-08", "Fed (États-Unis)", "Décision sur les taux, avec nouvelles prévisions économiques"),
]


def log(m):
    print(f"[calendrier] {m}", flush=True)


def _date(x):
    try:
        if hasattr(x, "date"):
            return x.date() if callable(x.date) else x.date
        return dt.date.fromisoformat(str(x)[:10])
    except Exception:
        return None


def evenements_entreprises(titres, rafraichir=False):
    """titres : liste de dicts {ticker, nom}. Résultat mis en cache une fois par jour."""
    import yfinance as yf
    aujourd_hui = dt.date.today().isoformat()
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    if cache.get("date") != aujourd_hui:
        cache = {"date": aujourd_hui, "titres": {}}
    for t in titres:
        tk = t["ticker"]
        if tk in cache["titres"] and not rafraichir:
            continue
        ev = []
        try:
            cal = yf.Ticker(tk).calendar or {}
            if isinstance(cal, dict):
                for d in (cal.get("Earnings Date") or [])[:1]:
                    dd = _date(d)
                    if dd:
                        ev.append({"date": dd.isoformat(), "type": "Résultats", "texte": f"Publication des résultats de {t['nom']}"})
                for cle, lib in (("Ex-Dividend Date", "Détachement du dividende"), ("Dividend Date", "Paiement du dividende")):
                    dd = _date(cal.get(cle)) if cal.get(cle) else None
                    if dd:
                        ev.append({"date": dd.isoformat(), "type": "Dividende", "texte": f"{lib} de {t['nom']}"})
        except Exception:
            pass
        cache["titres"][tk] = ev
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    sortie = []
    for t in titres:
        for e in cache["titres"].get(t["ticker"], []):
            sortie.append(e | {"ticker": t["ticker"], "nom": t["nom"]})
    return sortie


def a_venir(titres, jours=21):
    debut, fin = dt.date.today(), dt.date.today() + dt.timedelta(days=jours)
    ev = [e for e in evenements_entreprises(titres) if debut <= dt.date.fromisoformat(e["date"]) <= fin]
    for d, qui, texte in BANQUES_CENTRALES:
        dd = dt.date.fromisoformat(d)
        if debut <= dd <= fin:
            ev.append({"date": d, "type": "Banque centrale", "texte": f"{qui} : {texte}", "ticker": "", "nom": qui})
    ev.sort(key=lambda e: e["date"])
    return ev
