# -*- coding: utf-8 -*-
"""Newsletters SignalBourse : « Ta semaine » (lundi matin) et « Bilan de la semaine » (vendredi soir)."""

import datetime as dt
import html
import os
from pathlib import Path

import pandas as pd

import monde

DOSSIER = Path(__file__).resolve().parent
SITE = os.environ.get("SITE_URL", "https://holdingismaelkouloumba.github.io/signalbourse/")
COUL = {"ACHAT FORT": "#0a7d32", "ACHAT / RENFORCER": "#3aa655", "CONSERVER / ATTENDRE": "#8a8a8a",
        "ALLÉGER": "#d98a1c", "VENDRE": "#c62828"}

E = html.escape


def _badge(sig):
    return (f'<span style="background:{COUL.get(sig, "#888")};color:#fff;padding:2px 7px;border-radius:9px;'
            f'font-size:11px;font-weight:600;white-space:nowrap">{E(sig)}</span>')


def _pct(v):
    if v is None:
        return "—"
    return f'<b style="color:{"#0a7d32" if v >= 0 else "#c62828"}">{v:+.1%}</b>'


def _tableau(lignes, colonnes):
    th = "".join(f'<th style="text-align:left;padding:6px 8px;font-size:12px;color:#666;border-bottom:1px solid #ddd">{c}</th>' for c in colonnes)
    tr = "".join("<tr>" + "".join(f'<td style="padding:6px 8px;font-size:13px;border-bottom:1px solid #f0f0f0;vertical-align:top">{c}</td>' for c in l) + "</tr>" for l in lignes)
    return f'<table style="border-collapse:collapse;width:100%">{th and "<tr>" + th + "</tr>"}{tr}</table>'


def _titre(t):
    return f'<h2 style="font-size:17px;margin:26px 0 8px;color:#111">{t}</h2>'


def _nom(r):
    lieu = " · ".join(x for x in (r.get("pays"), r.get("secteur") or r.get("theme")) if x)
    new = " 🆕" if r.get("nouveau") else ""
    fonds = f'<br><span style="font-size:11px;color:#8a5a00">🏦 {E(", ".join(r["fonds_acheteurs"][:2]))}</span>' if r.get("fonds_acheteurs") else ""
    return f'<b>{E(r["nom"])}</b>{new}<br><span style="font-size:11px;color:#888">{E(r["ticker"])}{" · " + E(lieu) if lieu else ""}</span>{fonds}'


def _changements_semaine(actuels):
    """Signaux qui ont changé depuis une semaine, d'après l'historique."""
    f = DOSSIER / "historique_signaux.csv"
    if not f.exists():
        return []
    try:
        h = pd.read_csv(f)
        h["horodatage"] = pd.to_datetime(h["horodatage"], errors="coerce")
        limite = pd.Timestamp.now() - pd.Timedelta(days=6)
        anciens = h[h["horodatage"] <= limite].sort_values("horodatage").groupby("ticker").last()
        if anciens.empty:
            anciens = h.sort_values("horodatage").groupby("ticker").first()
    except Exception:
        return []
    sortie = []
    for r in actuels:
        if r["ticker"] in anciens.index:
            a = anciens.loc[r["ticker"]]
            for hz, lib in (("ct", "court terme"), ("lt", "long terme")):
                if str(a.get(f"signal_{hz}")) != r[f"signal_{hz}"]:
                    sortie.append((r, lib, str(a.get(f"signal_{hz}")), r[f"signal_{hz}"]))
    return sortie


def _gabarit(titre, intro, corps):
    return f"""<!DOCTYPE html><html><body style="margin:0;background:#f4f5f7;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#222">
<div style="max-width:680px;margin:0 auto;background:#fff;padding:24px 20px">
<h1 style="font-size:22px;margin:0">📈 {E(titre)}</h1>
<p style="color:#555;font-size:14px;margin:8px 0 0">{intro}</p>
<p style="margin:16px 0"><a href="{SITE}" style="background:#0b57d0;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-size:14px">Ouvrir le tableau de bord</a></p>
{corps}
<p style="font-size:11px;color:#888;margin-top:30px;border-top:1px solid #eee;padding-top:12px">Signaux générés automatiquement à partir de données publiques (Yahoo Finance, SEC). Outil d'aide à la décision, pas un conseil en investissement ; aucun signal n'est garanti.</p>
</div></body></html>"""


def lundi(resultats, extra):
    opps, pep, marches, fonds = extra.get("opportunites", []), extra.get("pepites", []), extra.get("marches", []), extra.get("fonds") or {}
    date = dt.date.today().strftime("%d/%m/%Y")
    achats = [r for r in resultats if r["score_lt"] >= 0.18 and r["score_ct"] > -0.18]
    prudence = [r for r in resultats if r["score_ct"] <= -0.18 or r["score_lt"] <= -0.18]
    corps = _titre("🌍 Les meilleures opportunités du moment")
    corps += _tableau([[_nom(r), _badge(r["signal_ct"]), _badge(r["signal_lt"]), _pct(r["perf"].get("1 mois")),
                        E("; ".join(r["raisons_pepite"][:2]))] for r in opps[:8]],
                      ["Titre", "Court terme", "Long terme", "1 mois", "Pourquoi"])
    corps += _titre("💎 Pépites à surveiller")
    corps += _tableau([[_nom(r), _badge(r["signal_ct"]), f'risque {monde_risque(r)}', _pct(r["perf"].get("3 mois"))] for r in pep[:6]],
                      ["Titre", "Court terme", "Risque", "3 mois"])
    corps += _titre("📋 Ma liste")
    corps += f'<p style="font-size:13px"><b>À acheter / renforcer :</b> {E(", ".join(r["nom"] for r in achats) or "aucune ligne cette semaine")}</p>'
    corps += f'<p style="font-size:13px"><b>Prudence :</b> {E(", ".join(r["nom"] for r in prudence) or "rien à signaler")}</p>'
    if marches:
        tri = sorted(marches, key=lambda r: -abs(r["score_ct"]))[:8]
        corps += _titre("🛢️ Matières premières & forex")
        corps += _tableau([[E(r["nom"]), _badge(r["signal_ct"]), _badge(r["signal_lt"]), _pct(r["perf"].get("1 sem."))] for r in tri],
                          ["Marché", "Court terme", "Long terme", "1 sem."])
    if fonds.get("fonds"):
        corps += _titre("🏦 Ce que les grands fonds ont acheté")
        lignes = [[E(f["nom"]), E(", ".join(p["nom"] for p in f["nouveaux"][:3]) or "—")] for f in fonds["fonds"] if f["nouveaux"]][:6]
        corps += _tableau(lignes, ["Fonds", "Nouvelles positions"])
    intro = f"Ta semaine boursière du {date} : {len(opps)} opportunités monde, {len(pep)} pépites, {len(achats)} lignes de ta liste à l'achat."
    return f"☀️ SignalBourse : ta semaine du {date}", _gabarit("Ta semaine boursière", intro, corps)


def monde_risque(r):
    v = r.get("vol_annuelle") or 0
    return "très élevé" if v > 0.6 else "élevé" if v > 0.4 else "moyen" if v > 0.25 else "modéré"


def bilan(resultats, extra):
    opps, pep, marches = extra.get("opportunites", []), extra.get("pepites", []), extra.get("marches", [])
    date = dt.date.today().strftime("%d/%m/%Y")
    sem = lambda r: r["perf"].get("1 sem.")
    liste = sorted([r for r in resultats if sem(r) is not None], key=lambda r: -sem(r))
    corps = _titre("📋 Ma liste cette semaine")
    corps += _tableau([[_nom(r), _pct(sem(r)), _badge(r["signal_ct"]), _badge(r["signal_lt"])] for r in liste],
                      ["Titre", "Semaine", "Court terme", "Long terme"])
    chg = _changements_semaine(resultats + opps + pep + marches)
    corps += _titre("🔄 Signaux qui ont changé")
    corps += _tableau([[_nom(r), lib, _badge(a) if a in COUL else E(a), _badge(n)] for r, lib, a, n in chg[:15]],
                      ["Titre", "Horizon", "Avant", "Maintenant"]) if chg else '<p style="font-size:13px">Aucun changement de signal cette semaine.</p>'
    tous = sorted([r for r in opps + pep if sem(r) is not None], key=lambda r: -sem(r))
    if tous:
        corps += _titre("🚀 Meilleures performances parmi les opportunités et pépites")
        corps += _tableau([[_nom(r), _pct(sem(r)), _pct(r["perf"].get("1 mois"))] for r in tous[:6]], ["Titre", "Semaine", "1 mois"])
        corps += _titre("📉 Plus fortes baisses")
        corps += _tableau([[_nom(r), _pct(sem(r)), _badge(r["signal_ct"])] for r in tous[-4:][::-1]], ["Titre", "Semaine", "Court terme"])
    nouveaux = [r for r in opps + pep if r.get("nouveau")]
    if nouveaux:
        corps += _titre("🆕 Entrées dans la liste cette semaine")
        corps += _tableau([[_nom(r), _badge(r["signal_lt"]), E("; ".join(r["raisons_pepite"][:2]))] for r in nouveaux[:8]],
                          ["Titre", "Long terme", "Pourquoi"])
    if marches:
        corps += _titre("🛢️ Matières premières & forex sur la semaine")
        corps += _tableau([[E(r["nom"]), _pct(sem(r)), _badge(r["signal_ct"])] for r in sorted(marches, key=lambda r: -(sem(r) or 0))],
                          ["Marché", "Semaine", "Court terme"])
    best = liste[0]["nom"] if liste else "—"
    intro = f"Bilan au {date} : {len(chg)} changements de signal, meilleure ligne de ta liste : {E(best)}."
    return f"📊 SignalBourse : bilan de la semaine ({date})", _gabarit("Bilan de la semaine", intro, corps)


def envoyer(quelle, resultats, extra):
    sujet, corps = (lundi if quelle == "lundi" else bilan)(resultats, extra)
    try:
        monde.envoyer_email(sujet, corps)
    except Exception as ex:
        print(f"[newsletter] échec de l'envoi : {ex}", flush=True)
