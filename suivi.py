# -*- coding: utf-8 -*-
"""Bulletin de notes : les signaux passés ont-ils eu raison ?"""

import datetime as dt
import json
from pathlib import Path

import pandas as pd

DOSSIER = Path(__file__).resolve().parent
HISTO = DOSSIER / "historique_signaux.csv"
CACHE_SIMU = DOSSIER / "simulation_cache.json"
REFERENCE = "CW8.PA"  # MSCI World, pour comparer
HORIZONS = [("1 semaine", 7), ("1 mois", 30), ("3 mois", 91)]
ORDRE = ["ACHAT FORT", "ACHAT / RENFORCER", "CONSERVER / ATTENDRE", "ALLÉGER", "VENDRE"]


def bulletin():
    """Pour chaque signal émis, évolution du cours après 1 semaine, 1 mois, 3 mois (d'après l'historique quotidien)."""
    if not HISTO.exists():
        return {"jours": 0, "tableau": {}}
    h = pd.read_csv(HISTO)
    h["horodatage"] = pd.to_datetime(h["horodatage"], errors="coerce")
    h = h.dropna(subset=["horodatage", "prix"])
    h["jour"] = h["horodatage"].dt.normalize()
    h = h.sort_values("horodatage").groupby(["ticker", "jour"]).last().reset_index()
    jours = int(h["jour"].nunique())
    ref = h[h["ticker"] == REFERENCE].set_index("jour")["prix"]

    def prix_apres(serie, jour, n):
        cible = jour + pd.Timedelta(days=n)
        apres = serie[serie.index >= cible]
        return float(apres.iloc[0]) if len(apres) else None

    tableau = {hz: {} for hz in ("ct", "lt")}
    for tk, g in h.groupby("ticker"):
        s = g.set_index("jour")["prix"]
        for _, row in g.iterrows():
            for hz in ("ct", "lt"):
                sig = row.get(f"signal_{hz}")
                for lib, n in HORIZONS:
                    p = prix_apres(s, row["jour"], n)
                    if p is None or not row["prix"]:
                        continue
                    rdt = p / row["prix"] - 1
                    rref = None
                    if len(ref):
                        p0, p1 = prix_apres(ref, row["jour"], 0), prix_apres(ref, row["jour"], n)
                        rref = (p1 / p0 - 1) if p0 and p1 else None
                    cell = tableau[hz].setdefault(sig, {}).setdefault(lib, {"n": 0, "gagnants": 0, "somme": 0.0, "somme_ref": 0.0, "n_ref": 0})
                    cell["n"] += 1
                    cell["somme"] += rdt
                    # pour un signal de vente, « avoir raison » = le cours a baissé
                    juste = rdt < 0 if sig in ("ALLÉGER", "VENDRE") else rdt > 0
                    cell["gagnants"] += int(juste)
                    if rref is not None:
                        cell["somme_ref"] += rref
                        cell["n_ref"] += 1
    propre = {}
    for hz, sigs in tableau.items():
        propre[hz] = []
        for sig in ORDRE:
            if sig not in sigs:
                continue
            ligne = {"signal": sig}
            for lib, _ in HORIZONS:
                c = sigs[sig].get(lib)
                ligne[lib] = None if not c or not c["n"] else {
                    "n": c["n"], "reussite": c["gagnants"] / c["n"], "moyenne": c["somme"] / c["n"],
                    "reference": (c["somme_ref"] / c["n_ref"]) if c["n_ref"] else None}
            propre[hz].append(ligne)
    return {"jours": jours, "tableau": propre, "debut": h["jour"].min().strftime("%d/%m/%Y") if jours else None}


def simulation(analyses, fn_historique, fn_backtest, rafraichir=False):
    """Simulation sur 5 ans : suivre les signaux court terme vs acheter et garder (mise en cache 1 jour)."""
    aujourd_hui = dt.date.today().isoformat()
    if CACHE_SIMU.exists() and not rafraichir:
        try:
            c = json.loads(CACHE_SIMU.read_text(encoding="utf-8"))
            if c.get("date") == aujourd_hui:
                return c["lignes"]
        except Exception:
            pass
    lignes = []
    for r in analyses:
        try:
            b = fn_backtest(fn_historique(r["ticker"], "5y"))
            lignes.append({"ticker": r["ticker"], "nom": r["nom"], "strategie": b["strategie"]["perf_annuelle"],
                           "garder": b["achat_conserve"]["perf_annuelle"], "baisse_strat": b["strategie"]["pire_baisse"],
                           "baisse_garder": b["achat_conserve"]["pire_baisse"], "trades": b["nb_trades"],
                           "reussite": b["taux_reussite"]})
        except Exception:
            continue
    CACHE_SIMU.write_text(json.dumps({"date": aujourd_hui, "lignes": lignes}, ensure_ascii=False), encoding="utf-8")
    return lignes
