# -*- coding: utf-8 -*-
"""Interface du tableau de bord SignalBourse : page principale à onglets + fiche détaillée par titre.
Tout est écrit en mots simples, sans jargon."""

import datetime as dt

JOURS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def jour_fr(iso):
    d = dt.date.fromisoformat(iso)
    return f"{JOURS_FR[d.weekday()]} {d.strftime('%d/%m')}"
import html
import json
import re

E = html.escape

COULEURS = {"ACHAT FORT": "#0a7d32", "ACHAT / RENFORCER": "#3aa655", "CONSERVER / ATTENDRE": "#8a8a8a",
            "ALLÉGER": "#d98a1c", "VENDRE": "#c62828"}
EXPLICATION_SIGNAL = {
    "ACHAT FORT": "Les indicateurs sont nettement favorables",
    "ACHAT / RENFORCER": "Plutôt favorable : on peut acheter ou en reprendre un peu",
    "CONSERVER / ATTENDRE": "Rien de décisif : garder si on l'a, sinon attendre",
    "ALLÉGER": "Plutôt défavorable : on peut en revendre une partie",
    "VENDRE": "Les indicateurs sont nettement défavorables",
}


def slug(ticker):
    return re.sub(r"[^A-Za-z0-9]+", "_", ticker).strip("_")


def risque(vol):
    if vol is None or vol != vol:
        return "inconnu"
    return "très élevé" if vol > 0.60 else "élevé" if vol > 0.40 else "moyen" if vol > 0.25 else "modéré"


def badge(sig, petit=False):
    return (f'<span class="badge{" petit-b" if petit else ""}" style="background:{COULEURS.get(sig, "#888")}" '
            f'title="{E(EXPLICATION_SIGNAL.get(sig, ""))}">{E(sig)}</span>')


def pct(v, gras=True):
    if v is None:
        return "—"
    cls = "up" if v >= 0 else "down"
    return f"<{'b' if gras else 'span'} class='{cls}'>{v:+.1%}</{'b' if gras else 'span'}>"


def nombre(v, dec=2):
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    if abs(v) < 1:
        return f"{v:.4g}"
    return f"{v:,.{dec}f}".replace(",", " ")


def spark(vals, l=120, h=34):
    if not vals or len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    e = (mx - mn) or 1
    pts = " ".join(f"{i * l / (len(vals) - 1):.1f},{h - (v - mn) / e * h:.1f}" for i, v in enumerate(vals))
    coul = "#0a7d32" if vals[-1] >= vals[0] else "#c62828"
    return f'<svg width="{l}" height="{h}" viewBox="0 0 {l} {h}" aria-hidden="true"><polyline fill="none" stroke="{coul}" stroke-width="1.6" points="{pts}"/></svg>'


def liens(news, n=4):
    if not news:
        return "<em class='petit'>Aucune actualité marquante</em>"
    return "<br>".join(f'<a href="{E(x["lien"])}" target="_blank" rel="noopener">{E(x["titre"][:130])}</a>' for x in news[:n])


def etoiles(score):
    n = max(1, min(5, int(round((score + 1) * 2.5))))
    return "★" * n + "☆" * (5 - n)


def perfs(r):
    return " · ".join(f"{k} {pct(v)}" for k, v in r.get("perf", {}).items())


# ----------------------------------------------------------------------------
# Carte d'un titre
# ----------------------------------------------------------------------------

def carte(r, rang=None, base_fiche="f/"):
    tags = []
    if r.get("nouveau"):
        tags.append('<span class="tag nouveau" title="Entré dans la liste il y a moins de 7 jours">🆕 Nouveau</span>')
    if r.get("fonds_acheteurs"):
        tags.append(f'<span class="tag fonds" title="A acheté ou renforcé ce titre au dernier trimestre">🏦 {E(", ".join(r["fonds_acheteurs"][:2]))}</span>')
    if r.get("pea") == "PEA":
        tags.append('<span class="tag pea" title="Peut se loger dans un PEA">PEA ✓</span>')
    elif r.get("pea") == "Compte-titres":
        tags.append('<span class="tag cto" title="Nécessite un compte-titres">Compte-titres</span>')
    if r.get("dividende"):
        tags.append(f'<span class="tag div">Dividende {r["dividende"]:.1%}</span>')
    lieu = " · ".join(x for x in (r.get("pays") or r.get("pays_siege"), r.get("secteur") or r.get("theme")) if x) or r["type"]
    protection = "" if r["type"] in ("Forex",) else (
        f'<div class="petit">🛡️ Seuil de protection : <b>{nombre(r["stop"])}</b> · 🎯 Objectif : <b>{nombre(r["objectif"])}</b>'
        + (f' · Quantité max conseillée : <b>{r["quantite"]}</b>' if r["type"] in ("Action", "ETF", "Obligations") else "") + "</div>")
    meilleures = "".join(f"<li>{E(x)}</li>" for x in r.get("raisons_pepite", [])[:3])
    return f"""
<div class="carte" data-type="{E(r['type'])}" data-zone="{E(r.get('zone', ''))}" data-secteur="{E(r.get('secteur', ''))}"
 data-pea="{E(r.get('pea', ''))}" data-div="{(r.get('dividende') or 0):.4f}" data-pot="{r.get('score_pepite', 0):.3f}"
 data-lt="{r.get('score_lt', 0):.3f}" data-vol="{(r.get('vol_annuelle') or 0):.3f}">
  <div class="haut">
    <div><div class="nom">{f'#{rang} ' if rang else ''}{E(r['nom'])}</div><div class="petit">{E(r['ticker'])} · {E(lieu)}</div></div>
    <div class="prix">{nombre(r['prix'])} <small>{E(r.get('devise', ''))}</small><br>{spark(r.get('spark'))}</div>
  </div>
  {('<div class="tags">' + ''.join(tags) + '</div>') if tags else ''}
  <div class="pep"><span class="etoiles" title="Potentiel de hausse à venir">{etoiles(r.get('score_pepite', 0))}</span> potentiel · risque <b>{risque(r.get('vol_annuelle'))}</b></div>
  <div class="petit">{perfs(r)}</div>
  <div class="signaux">
    <div><div class="petit">Court terme (jours / semaines)</div>{badge(r['signal_ct'])}</div>
    <div><div class="petit">Long terme (mois / années)</div>{badge(r['signal_lt'])}</div>
  </div>
  {protection}
  <ul class="raisons">{meilleures}</ul>
  <a class="fiche" href="{base_fiche}{slug(r['ticker'])}.html">Voir la fiche complète →</a>
</div>"""


# ----------------------------------------------------------------------------
# Résumé du jour (accueil)
# ----------------------------------------------------------------------------

def resume_du_jour(data):
    phrases = []
    liste = data.get("liste", [])
    ref = next((r for r in liste if r["ticker"] == "CW8.PA"), None)
    if ref and ref["perf"].get("1 sem.") is not None:
        p = ref["perf"]["1 sem."]
        humeur = ("Les marchés mondiaux montent nettement" if p > 0.02 else "Les marchés mondiaux progressent légèrement" if p > 0
                  else "Les marchés mondiaux reculent légèrement" if p > -0.02 else "Les marchés mondiaux baissent nettement")
        phrases.append(f"{humeur} cette semaine ({p:+.1%} pour l'ETF MSCI World).")
    achats = [r for r in liste if r["score_lt"] >= 0.18]
    prudence = [r for r in liste if r["score_ct"] <= -0.18]
    if liste:
        phrases.append(f"Dans ta liste, {len(achats)} lignes sur {len(liste)} sont favorables à long terme"
                       + (f" et {len(prudence)} demandent de la prudence à court terme." if prudence else "."))
    opps = data.get("opportunites", [])
    if opps:
        top = ", ".join(r["nom"] for r in opps[:3])
        phrases.append(f"Les opportunités les mieux classées aujourd'hui : {top}.")
    nouveaux = [r for r in opps + data.get("pepites", []) + data.get("cryptos", []) if r.get("nouveau")]
    if nouveaux:
        phrases.append(f"{len(nouveaux)} nouveaux titres sont entrés dans les listes cette semaine (badge 🆕).")
    marches = {r["ticker"]: r for r in data.get("marches", [])}
    morceaux = []
    for tk, nom in (("GC=F", "l'or"), ("BZ=F", "le pétrole"), ("EURUSD=X", "l'euro face au dollar")):
        r = marches.get(tk)
        if r and r["perf"].get("1 sem.") is not None:
            morceaux.append(f"{nom} {r['perf']['1 sem.']:+.1%}")
    if morceaux:
        phrases.append("Sur la semaine : " + ", ".join(morceaux) + ".")
    btc = next((r for r in data.get("cryptos", []) if r["ticker"] == "BTC-USD"), None)
    if btc and btc["perf"].get("1 sem.") is not None:
        phrases.append(f"Le bitcoin évolue de {btc['perf']['1 sem.']:+.1%} sur 7 jours.")
    ev = [e for e in data.get("calendrier", []) if e["date"] <= (dt.date.today() + dt.timedelta(days=7)).isoformat()]
    if ev:
        phrases.append("À surveiller dans les 7 jours : " + "; ".join(f"{e['texte']} ({dt.date.fromisoformat(e['date']).strftime('%d/%m')})" for e in ev[:4]) + ".")
    return " ".join(phrases)


# ----------------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------------

def section_portefeuille(pf, base_fiche="f/"):
    if not pf:
        return """<div class="encart"><b>Ajoute ton portefeuille pour suivre tes gains, ta répartition et recevoir des alertes sur TES lignes.</b>
<p>Sur GitHub : Settings > Secrets and variables > Actions > New repository secret. Nom : <code>PORTEFEUILLE</code>. Valeur : une ligne par position, sous la forme <code>TICKER;QUANTITÉ;PRIX D'ACHAT</code>, par exemple :</p>
<pre>CW8.PA;3;512.40
MC.PA;2;610
BTC-USD;0.01;58000;Crypto
LIQUIDITES;1500</pre><p class="petit">Le secret reste invisible, même si le dépôt est public.</p></div>"""
    rep = "".join(f"<div class='barre'><span>{E(k)}</span><div class='jauge'><i style='width:{v * 100:.0f}%'></i></div><b>{v:.0%}</b></div>"
                  for k, v in sorted(pf["repartition"].items(), key=lambda x: -x[1]))
    pays = "".join(f"<div class='barre'><span>{E(k)}</span><div class='jauge'><i style='width:{v * 100:.0f}%'></i></div><b>{v:.0%}</b></div>"
                   for k, v in list(pf["pays"].items())[:6])
    lignes = "".join(f"""<tr><td><a href="{base_fiche}{slug(l['r']['ticker'])}.html"><b>{E(l['r']['nom'])}</b></a><br><span class="petit">{E(l['r']['ticker'])}</span></td>
<td>{nombre(l['quantite'], 4)}</td><td>{nombre(l['prix_achat'])} → <b>{nombre(l['r']['prix'])}</b></td><td>{nombre(l['valeur'], 0)} €</td>
<td>{pct(l['gain_pct'])}<br><span class="petit">{l['gain']:+,.0f} €</span></td><td>{l['poids']:.0%}</td><td>{badge(l['r']['signal_lt'], True)}</td></tr>""".replace(",", " ")
                     for l in pf["lignes"])
    conseils = "".join(f"<li>{E(c)}</li>" for c in pf["conseils"])
    return f"""
<div class="kpis">
  <div class="kpi"><div class="petit">Valeur totale</div><div class="gros">{pf['total']:,.0f} €</div></div>
  <div class="kpi"><div class="petit">Gain ou perte</div><div class="gros">{pct(pf['gain_pct'])}</div><div class="petit">{pf['gain']:+,.0f} € sur {pf['investi']:,.0f} € investis</div></div>
  <div class="kpi"><div class="petit">Liquidités</div><div class="gros">{pf['liquidites']:,.0f} €</div></div>
</div>
<h3>💡 Ce que je te conseille de regarder</h3><ul class="conseils">{conseils}</ul>
<div class="deux"><div class="encart"><h3>Répartition par type</h3>{rep}<p class="petit">Cible pour ton profil : environ 75 % actions, 20 % obligations, 5 % or.</p></div>
<div class="encart"><h3>Répartition par pays</h3>{pays}</div></div>
<h3>Tes lignes</h3><div class="tableau"><table><tr><th>Titre</th><th>Quantité</th><th>Prix d'achat → actuel</th><th>Valeur</th><th>Gain</th><th>Poids</th><th>Signal long terme</th></tr>{lignes}</table></div>
""".replace(",", " ")


def section_calendrier(ev):
    if not ev:
        return "<p class='petit'>Aucun événement important dans les 3 prochaines semaines pour tes titres.</p>"
    lignes = "".join(f"<tr><td><b>{jour_fr(e['date'])}</b></td><td>{E(e['type'])}</td><td>{E(e['texte'])}</td></tr>"
                     for e in ev[:25])
    return f"<div class='tableau'><table><tr><th>Date</th><th>Type</th><th>Événement</th></tr>{lignes}</table></div>"


def section_alertes(alertes):
    if not alertes:
        return "<p class='petit'>Aucune alerte aujourd'hui.</p>"
    return "<ul class='alertes'>" + "".join(f"<li>{E(a)}</li>" for a in alertes[:15]) + "</ul>"


def section_fonds(fonds):
    if not fonds or not fonds.get("fonds"):
        return "<p class='petit'>Données des grands investisseurs indisponibles pour le moment.</p>"
    out = []
    for f in fonds["fonds"]:
        def liste(items, fmt):
            return "<ul>" + "".join(f"<li>{fmt(i)}</li>" for i in items) + "</ul>" if items else "<p class='petit'>—</p>"
        out.append(f"""<div class="carte"><div class="nom">{E(f['nom'])}</div>
<div class="petit">Positions : {E(str(f.get('trimestre', '')))} · publiées le {E(str(f.get('publie', '')))}</div>
<details open><summary>🆕 Nouveaux achats</summary>{liste(f['nouveaux'], lambda i: f"{E(i['nom'])} <span class='petit'>({i.get('poids', 0):.1%} du portefeuille)</span>")}</details>
<details><summary>⬆️ Positions renforcées</summary>{liste(f['renforces'], lambda i: f"{E(i['nom'])} <b class='up'>{i['var']:+.0%}</b>")}</details>
<details><summary>⬇️ Positions allégées</summary>{liste(f['alleges'], lambda i: f"{E(i['nom'])} <b class='down'>{i['var']:+.0%}</b>")}</details>
<details><summary>🏆 Plus grosses positions</summary>{liste(f['top'], lambda i: f"{E(i['nom'])} <span class='petit'>{i.get('poids', 0):.1%}</span>")}</details></div>""")
    return "".join(out)


def section_afrique(af, base_fiche="f/"):
    out = []
    b = af.get("brvm") or {}
    if b.get("titres"):
        lignes = "".join(f"<tr><td><b>{E(t['symbole'])}</b><br><span class='petit'>{E(t['nom'])}</span></td><td>{nombre(t['cours'], 0)} FCFA</td>"
                         f"<td>{pct(t['variation_jour'])}</td><td>{pct(t['perf_1sem'])}</td><td>{pct(t['perf_1mois'])}</td>"
                         f"<td>{E({'hausse': '📈 en hausse', 'baisse': '📉 en baisse', 'stable': '➖ stable'}.get(t['tendance'] or '', '—'))}</td></tr>"
                         for t in b["titres"])
        out.append(f"<h3>🇨🇮 BRVM (Abidjan, 8 pays d'Afrique de l'Ouest)</h3><p class='petit'>{E(b.get('message', ''))}</p>"
                   f"<div class='tableau'><table><tr><th>Titre</th><th>Cours</th><th>Jour</th><th>1 sem.</th><th>1 mois</th><th>Tendance</th></tr>{lignes}</table></div>")
    else:
        out.append(f"<h3>🇨🇮 BRVM (Abidjan)</h3><p class='petit'>{E(b.get('message', 'Données BRVM indisponibles pour le moment.'))}</p>")
    if af.get("actions"):
        out.append("<h3>🇿🇦🇪🇬 Meilleures actions d'Afrique du Sud et d'Égypte</h3><div class='grille'>"
                   + "".join(carte(r, i + 1, base_fiche) for i, r in enumerate(af["actions"])) + "</div>")
    if af.get("devises"):
        out.append("<h3>💱 Devises africaines</h3><div class='grille'>" + "".join(carte(r, None, base_fiche) for r in af["devises"]) + "</div>")
    out.append("<p class='petit'>Les bourses de Lagos, Casablanca, Nairobi et la BVMAC (Douala) ne sont pas disponibles gratuitement.</p>")
    return "".join(out)


def section_bulletin(bul, simu):
    out = []
    j = bul.get("jours", 0) if bul else 0
    if bul and bul.get("tableau", {}).get("lt"):
        def tab(lignes, titre):
            th = "".join(f"<th>{h}</th>" for h in ("Signal", "Après 1 semaine", "Après 1 mois", "Après 3 mois"))
            tr = ""
            for l in lignes:
                cases = []
                for hz in ("1 semaine", "1 mois", "3 mois"):
                    c = l.get(hz)
                    cases.append("<span class='petit'>pas encore assez de recul</span>" if not c else
                                 f"Juste {c['reussite']:.0%} du temps<br>Évolution moyenne {pct(c['moyenne'])}"
                                 + (f"<br><span class='petit'>Marché mondial : {pct(c['reference'], False)}</span>" if c.get("reference") is not None else "")
                                 + f"<br><span class='petit'>{c['n']} signaux</span>")
                tr += f"<tr><td>{badge(l['signal'], True)}</td>" + "".join(f"<td>{x}</td>" for x in cases) + "</tr>"
            return f"<h3>{titre}</h3><div class='tableau'><table><tr>{th}</tr>{tr}</table></div>"
        out.append(f"<p>Suivi réel depuis le {E(bul.get('debut') or '—')} ({j} jours de données). « Juste » veut dire : le cours a monté après un signal d'achat, ou baissé après un signal de vente.</p>")
        out.append(tab(bul["tableau"]["lt"], "Signaux long terme"))
        out.append(tab(bul["tableau"]["ct"], "Signaux court terme"))
    else:
        out.append(f"<div class='encart'>Le suivi réel démarre : il faut quelques semaines de données pour mesurer si les signaux ont eu raison ({j} jour(s) enregistrés pour l'instant).</div>")
    if simu:
        tr = "".join(f"<tr><td><b>{E(s['nom'])}</b></td><td>{pct(s['strategie'])}</td><td>{pct(s['garder'])}</td>"
                     f"<td>{pct(s['baisse_strat'], False)} / {pct(s['baisse_garder'], False)}</td><td>{s['reussite']:.0%} ({s['trades']})</td></tr>" for s in simu)
        gagne = sum(1 for s in simu if s["strategie"] > s["garder"])
        out.append(f"""<h3>Simulation sur 5 ans : suivre les signaux court terme ou acheter et garder ?</h3>
<p class="petit">Performance moyenne par an, frais de 0,1 % par ordre inclus. Les signaux font mieux sur {gagne} titres sur {len(simu)}.
Souvent, « acheter et garder » gagne sur les titres qui montent fort, mais les signaux limitent les grosses baisses.</p>
<div class='tableau'><table><tr><th>Titre</th><th>En suivant les signaux</th><th>En gardant</th><th>Pire baisse (signaux / garder)</th><th>Opérations gagnantes</th></tr>{tr}</table></div>""")
    return "".join(out)


METHODE = """
<p><b>Les deux signaux</b></p>
<ul>
<li><b>Court terme</b> (quelques jours à quelques semaines) : regarde surtout l'évolution récente du cours (tendance des dernières semaines, élan, surchauffe ou non) et l'actualité des 14 derniers jours.</li>
<li><b>Long terme</b> (plusieurs mois à plusieurs années) : regarde la santé de l'entreprise (ventes, bénéfices, rentabilité, dettes, trésorerie), son prix par rapport à ses bénéfices, l'avis des analystes, la tendance de fond, l'actualité et les décisions des dirigeants.</li>
</ul>
<p><b>Les étoiles de potentiel</b> mesurent le potentiel de hausse <i>à venir</i>, et pas seulement ce qui a déjà monté : croissance attendue des bénéfices et des ventes, qualité de l'entreprise, prix raisonnable par rapport à sa croissance, objectif des analystes, et bon moment d'achat. Un titre qui a déjà énormément monté perd des points ; un titre solide qui commence juste à remonter en gagne.</p>
<p><b>Seuil de protection</b> : niveau sous lequel il est prudent de vendre pour limiter la perte. Il est placé à environ deux fois la variation habituelle du cours en dessous du prix actuel.
<b>Objectif</b> : niveau de prise de bénéfice raisonnable, à environ trois fois la variation habituelle au-dessus.
<b>Quantité max conseillée</b> : nombre de titres à acheter au maximum pour ne pas perdre plus de 1 % de ton capital si le seuil de protection est touché.</p>
<p><b>Le risque</b> mesure l'ampleur habituelle des variations : modéré, moyen, élevé, très élevé.</p>
<p><b>Les listes se renouvellent seules</b> : chaque jour, l'appli passe en revue environ 1 300 actions dans 30 pays, les ETF mondiaux et les 250 premières cryptos. Elle garde les meilleures, en limitant le nombre de titres par pays et par secteur pour rester diversifiée.</p>
<p><b>PEA ✓</b> : action d'une entreprise européenne cotée en Europe, en principe éligible au PEA. Pour les ETF, vérifie chez ton courtier.</p>
<p><b>Sources</b> : Yahoo Finance, CoinGecko, Dataroma (positions des grands investisseurs), BRVM, Google Actualités. Toutes sont gratuites et à usage personnel.</p>
<p><b>Conformité</b> : respecte la politique de ton employeur sur les transactions personnelles. N'utilise jamais une information non publique sur un client.</p>
"""


CSS = """
:root{--bg:#f6f7f9;--carte:#fff;--txt:#1d1d1f;--muted:#6b6f76;--bord:#e4e6ea;--accent:#0b57d0}
@media (prefers-color-scheme: dark){:root{--bg:#121316;--carte:#1c1e22;--txt:#ececef;--muted:#9a9ea6;--bord:#2d3036;--accent:#7aa7ff}}
*{box-sizing:border-box} body{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--txt);line-height:1.4}
header{padding:16px 16px 4px;max-width:1240px;margin:auto} h1{margin:0;font-size:24px} main{max-width:1240px;margin:auto;padding:0 16px 50px}
.onglets{display:flex;gap:6px;margin:10px 0;overflow-x:auto;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:3;scrollbar-width:none}
.onglets button{flex:0 0 auto;border:1px solid var(--bord);background:var(--carte);color:var(--txt);padding:8px 13px;border-radius:20px;font-size:14px;cursor:pointer}
.onglets button.actif{background:var(--accent);color:#fff;border-color:var(--accent)}
.filtres{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;align-items:center} .filtres button{font-size:12px;padding:5px 10px;border-radius:14px;border:1px solid var(--bord);background:transparent;color:var(--txt);cursor:pointer}
.filtres button.actif{background:var(--txt);color:var(--bg)} .filtres select,.filtres label{font-size:13px;color:var(--txt)} .filtres select{padding:5px;border-radius:8px;border:1px solid var(--bord);background:var(--carte)}
.grille{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.carte{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:7px}
.haut{display:flex;justify-content:space-between;gap:8px} .nom{font-weight:600} .prix{text-align:right;font-variant-numeric:tabular-nums}
.petit{font-size:12px;color:var(--muted)} .signaux{display:flex;gap:14px;flex-wrap:wrap}
.badge{color:#fff;padding:3px 9px;border-radius:10px;font-size:12px;font-weight:600;display:inline-block;margin-top:2px;cursor:help} .petit-b{font-size:11px;padding:2px 7px}
.up{color:#0a7d32} .down{color:#c62828} @media (prefers-color-scheme: dark){.up{color:#4ade80}.down{color:#f87171}}
.pep{font-size:13px} .etoiles{color:#e0a800;letter-spacing:1px}
.tags{display:flex;flex-wrap:wrap;gap:4px} .tag{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}
.nouveau{background:#e8f0fe;color:#0b57d0} .fonds{background:#fdf1dc;color:#8a5a00} .pea{background:#e6f4ea;color:#137333} .cto{background:#f1f3f4;color:#5f6368} .div{background:#f3e8fd;color:#7b1fa2}
@media (prefers-color-scheme: dark){.nouveau{background:#1d2a44;color:#9cc0ff}.fonds{background:#3a2c10;color:#ffd38a}.pea{background:#16301f;color:#81c995}.cto{background:#2a2c30;color:#bdc1c6}.div{background:#2d1b3a;color:#d7aefb}}
.raisons{margin:0;padding-left:18px;font-size:13px} .fiche{font-size:14px;color:var(--accent);text-decoration:none;font-weight:600}
a{color:var(--accent);text-decoration:none} details summary{cursor:pointer;color:var(--accent);font-size:14px} details ul{margin:4px 0;padding-left:18px;font-size:13px}
.avert{background:#fff4e5;color:#5a3b00;padding:10px 12px;border-radius:10px;font-size:13px;margin:8px 0} @media (prefers-color-scheme: dark){.avert{background:#3a2c10;color:#ffdca3}}
.panneau{display:none} .panneau.actif{display:block} h3{margin:18px 0 8px;font-size:17px}
.encart{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:14px;font-size:14px}
.resume{font-size:16px;line-height:1.6;background:var(--carte);border:1px solid var(--bord);border-left:4px solid var(--accent);border-radius:12px;padding:14px 16px}
.tableau{overflow-x:auto;background:var(--carte);border:1px solid var(--bord);border-radius:12px} table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--bord);text-align:left;vertical-align:top} th{font-size:12px;color:var(--muted);font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px} .kpi{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:14px} .gros{font-size:24px;font-weight:600}
.deux{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px}
.barre{display:grid;grid-template-columns:150px 1fr 44px;gap:8px;align-items:center;font-size:13px;margin:5px 0} .jauge{background:var(--bord);border-radius:6px;height:10px;overflow:hidden} .jauge i{display:block;height:100%;background:var(--accent)}
.alertes li,.conseils li{margin:4px 0;font-size:14px} pre{background:var(--bg);padding:10px;border-radius:8px;font-size:13px}
.vide{display:none}
"""


def page(data, maintenant=None):
    """data : liste, portefeuille, opportunites, etfs, pepites, cryptos, afrique, marches, fonds, calendrier, alertes,
    bulletin, simulation, erreurs, actus_marche."""
    maintenant = maintenant or dt.datetime.now().strftime("%d/%m/%Y à %H:%M")
    liste = sorted(data.get("liste", []), key=lambda r: -(r["score_ct"] + r["score_lt"]))
    opps, etfs, pep, cryp = data.get("opportunites", []), data.get("etfs", []), data.get("pepites", []), data.get("cryptos", [])
    marches, af, pf = data.get("marches", []), data.get("afrique") or {}, data.get("portefeuille")
    secteurs = sorted({r.get("secteur") for r in opps + pep if r.get("secteur")})
    nb_pays = len({r.get("pays") for r in opps if r.get("pays")})
    onglets = [("accueil", "🏠 Accueil", True), ("portefeuille", "💼 Mon portefeuille", True), ("liste", "📋 Ma liste", bool(liste)),
               ("monde", "🌍 Opportunités monde", bool(opps or etfs)), ("pepites", "💎 Pépites", bool(pep)), ("crypto", "🪙 Crypto", bool(cryp)),
               ("afrique", "🌍 Afrique", bool(af)), ("marches", "🛢️ Matières & devises", bool(marches)),
               ("fonds", "🏦 Grands investisseurs", bool(data.get("fonds"))), ("bulletin", "📊 Bulletin de notes", True), ("methode", "❓ Méthode", True)]
    nav = "".join(f'<button data-onglet="{i}"{" class=actif" if i == "accueil" else ""}>{t}</button>' for i, t, ok in onglets if ok)
    actus = liens(data.get("actus_marche", []), 6)
    filtres_monde = f"""<div class="filtres" data-cible="g-monde">
  <button class="actif" data-f="tout">Tout</button><button data-attr="zone" data-f="Amériques">Amériques</button><button data-attr="zone" data-f="Europe">Europe</button>
  <button data-attr="zone" data-f="Asie-Pacifique">Asie-Pacifique</button><button data-attr="zone" data-f="Afrique &amp; Moyen-Orient">Afrique &amp; Moyen-Orient</button>
  <select data-filtre="secteur"><option value="">Tous les secteurs</option>{''.join(f'<option>{E(s)}</option>' for s in secteurs)}</select>
  <label><input type="checkbox" data-filtre="pea"> PEA seulement</label>
  <label><input type="checkbox" data-filtre="div"> Avec dividende</label>
  <select data-tri><option value="pot">Trier par potentiel</option><option value="lt">Trier par signal long terme</option><option value="div">Trier par dividende</option><option value="vol">Risque le plus faible</option></select>
</div>"""
    corps = f"""
<section class="panneau actif" id="accueil">
  <h3>☀️ Le résumé du jour</h3><div class="resume">{E(resume_du_jour(data))}</div>
  <div class="deux">
    <div class="encart"><h3>🔔 Alertes</h3>{section_alertes(data.get('alertes', []))}</div>
    <div class="encart"><h3>📰 Actualité des marchés</h3><div style="font-size:13px">{actus}</div></div>
  </div>
  <h3>📅 Les 3 prochaines semaines</h3>{section_calendrier(data.get('calendrier', []))}
  <h3>⭐ Le top du jour</h3><div class="grille">{''.join(carte(r, i + 1) for i, r in enumerate((opps[:3] + pep[:2] + cryp[:1])))}</div>
</section>
<section class="panneau" id="portefeuille">{section_portefeuille(pf)}</section>
<section class="panneau" id="liste">
  <div class="filtres" data-cible="g-liste"><button class="actif" data-f="tout">Tout</button><button data-f="Action">Actions</button><button data-f="ETF">ETF</button><button data-f="Obligations">Obligations</button></div>
  <div class="grille" id="g-liste">{''.join(carte(r) for r in liste)}</div>
</section>
<section class="panneau" id="monde">
  <p class="petit">Renouvelée chaque jour : {len(opps)} grandes entreprises de {nb_pays} pays, choisies pour leur potentiel de croissance à venir (bilan solide, croissance attendue, prix raisonnable, bon moment d'achat).</p>
  {filtres_monde}<div class="grille" id="g-monde">{''.join(carte(r, i + 1) for i, r in enumerate(opps))}</div>
  {('<h3>📊 ETF les plus prometteurs</h3><p class="petit">ETF de plus d’un milliard d’euros d’encours, sans effet de levier, accessibles depuis la France.</p><div class="grille">' + ''.join(carte(r, i + 1) for i, r in enumerate(etfs)) + '</div>') if etfs else ''}
</section>
<section class="panneau" id="pepites">
  <p class="petit">Entreprises de taille moyenne avec un fort potentiel de croissance, détectées dans le monde entier, plus ta liste perso. Plus risquées : 1 à 2 % de ton capital maximum par ligne.</p>
  <div class="filtres" data-cible="g-pep"><button class="actif" data-f="tout">Tout</button><button data-f="Action">Actions</button><button data-f="ETF">ETF</button>
  <label><input type="checkbox" data-filtre="pea"> PEA seulement</label></div>
  <div class="grille" id="g-pep">{''.join(carte(r, i + 1) for i, r in enumerate(pep))}</div>
</section>
<section class="panneau" id="crypto">
  <div class="avert">Les cryptos sont extrêmement risquées : elles peuvent perdre 50 à 90 % de leur valeur. N'y mets que de l'argent que tu peux te permettre de perdre (5 % maximum de ton patrimoine conseillé).</div>
  <p class="petit">Le bitcoin et l'ether comme repères, puis une sélection automatique parmi les 250 premières cryptos (pas seulement les plus grosses). Elles sont choisies pour leur reprise récente, des échanges suffisants et une marge de remontée par rapport à leur record.</p>
  <div class="grille">{''.join(carte(r, i + 1) for i, r in enumerate(cryp))}</div>
</section>
<section class="panneau" id="afrique">{section_afrique(af)}</section>
<section class="panneau" id="marches">
  <p class="petit">Matières premières (contrats à terme) et devises : marchés très volatils, souvent traités avec effet de levier. Prudence.</p>
  <div class="filtres" data-cible="g-marches"><button class="actif" data-f="tout">Tout</button><button data-f="Matières premières">Matières premières</button><button data-f="Forex">Devises</button></div>
  <div class="grille" id="g-marches">{''.join(carte(r) for r in sorted(marches, key=lambda x: -(x["score_ct"] + x["score_lt"])))}</div>
</section>
<section class="panneau" id="fonds"><p class="petit">Ce que les plus grands investisseurs ont acheté et vendu au dernier trimestre, d'après leurs déclarations officielles (publiées avec environ 45 jours de retard).</p><div class="grille">{section_fonds(data.get('fonds'))}</div></section>
<section class="panneau" id="bulletin">{section_bulletin(data.get('bulletin'), data.get('simulation'))}</section>
<section class="panneau" id="methode"><div class="encart">{METHODE}
{('<p><b>Titres introuvables</b> (ticker à vérifier sur finance.yahoo.com) : ' + E(', '.join(data.get('erreurs', [])[:30])) + '</p>') if data.get('erreurs') else ''}</div></section>
"""
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SignalBourse</title><meta name="theme-color" content="#0b57d0"><style>{CSS}</style></head><body>
<header><h1>📈 SignalBourse</h1><p class="petit">Mis à jour le {maintenant} · actualisé toutes les heures en semaine</p></header>
<main>
<div class="avert">Outil d'aide à la décision, <b>pas un conseil en investissement</b>. Aucun signal n'est garanti : tu peux perdre tout ou partie de ton capital. Données publiques gratuites, parfois avec 15 minutes de retard.</div>
<nav class="onglets">{nav}</nav>
{corps}
</main>
<script>
const montrer = id => {{
  document.querySelectorAll('.onglets button').forEach(x => x.classList.toggle('actif', x.dataset.onglet === id));
  document.querySelectorAll('.panneau').forEach(p => p.classList.toggle('actif', p.id === id));
  history.replaceState(null, '', '#' + id);
}};
document.querySelectorAll('.onglets button').forEach(b => b.onclick = () => montrer(b.dataset.onglet));
if (location.hash && document.getElementById(location.hash.slice(1))) montrer(location.hash.slice(1));
document.querySelectorAll('.filtres').forEach(f => {{
  const grille = document.getElementById(f.dataset.cible);
  if (!grille) return;
  const etat = {{attr: null, val: null}};
  const appliquer = () => {{
    const sect = f.querySelector('[data-filtre=secteur]')?.value || '';
    const pea = f.querySelector('[data-filtre=pea]')?.checked;
    const dv = f.querySelector('[data-filtre=div]')?.checked;
    grille.querySelectorAll('.carte').forEach(c => {{
      let ok = !etat.val || c.dataset[etat.attr] === etat.val;
      if (sect && c.dataset.secteur !== sect) ok = false;
      if (pea && c.dataset.pea !== 'PEA') ok = false;
      if (dv && !(parseFloat(c.dataset.div) > 0)) ok = false;
      c.style.display = ok ? '' : 'none';
    }});
    const tri = f.querySelector('[data-tri]')?.value;
    if (tri) {{
      const cartes = [...grille.querySelectorAll('.carte')];
      cartes.sort((a, b) => tri === 'vol' ? a.dataset.vol - b.dataset.vol : b.dataset[tri] - a.dataset[tri]);
      cartes.forEach(c => grille.appendChild(c));
    }}
  }};
  f.querySelectorAll('button').forEach(b => b.onclick = () => {{
    f.querySelectorAll('button').forEach(x => x.classList.toggle('actif', x === b));
    etat.attr = b.dataset.f === 'tout' ? null : (b.dataset.attr || 'type');
    etat.val = b.dataset.f === 'tout' ? null : b.dataset.f;
    appliquer();
  }});
  f.querySelectorAll('select, input').forEach(x => x.onchange = appliquer);
}});
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {{}});
</script></body></html>"""


# ----------------------------------------------------------------------------
# Fiche détaillée d'un titre
# ----------------------------------------------------------------------------

def graphique(courbe):
    if not courbe or len(courbe.get("cours", [])) < 10:
        return "<p class='petit'>Graphique indisponible.</p>"
    return f"""<div id="graph" style="position:relative"><svg id="svg" width="100%" height="300" role="img" aria-label="Évolution du cours sur 2 ans"></svg>
<div id="bulle" style="position:absolute;display:none;background:var(--carte);border:1px solid var(--bord);border-radius:8px;padding:6px 8px;font-size:12px;pointer-events:none"></div></div>
<p class="petit"><span style="color:var(--accent)">━</span> cours · <span style="color:#e0a800">━</span> moyenne des 50 derniers jours · <span style="color:#9a9ea6">━</span> moyenne des 200 derniers jours (tendance de fond)</p>
<script>
const C = {json.dumps(courbe)};
function dessiner(){{
  const svg = document.getElementById('svg'), W = svg.clientWidth || 600, H = 300, m = {{g: 48, d: 10, h: 10, b: 26}};
  const tous = C.cours.concat(C.m50.filter(x => x), C.m200.filter(x => x));
  const mn = Math.min(...tous), mx = Math.max(...tous), n = C.cours.length;
  const X = i => m.g + i * (W - m.g - m.d) / (n - 1), Y = v => m.h + (mx - v) * (H - m.h - m.b) / ((mx - mn) || 1);
  const ligne = (arr, coul, ep) => '<polyline fill="none" stroke="' + coul + '" stroke-width="' + ep + '" points="' + arr.map((v, i) => v == null ? '' : X(i).toFixed(1) + ',' + Y(v).toFixed(1)).filter(Boolean).join(' ') + '"/>';
  let g = '';
  for (let k = 0; k <= 4; k++) {{ const v = mn + (mx - mn) * k / 4, y = Y(v);
    g += '<line x1="' + m.g + '" x2="' + (W - m.d) + '" y1="' + y + '" y2="' + y + '" stroke="var(--bord)"/><text x="4" y="' + (y + 4) + '" font-size="11" fill="var(--muted)">' + (v >= 100 ? v.toFixed(0) : v.toPrecision(3)) + '</text>'; }}
  [0, Math.floor(n / 2), n - 1].forEach(i => g += '<text x="' + Math.min(X(i), W - 70) + '" y="' + (H - 6) + '" font-size="11" fill="var(--muted)">' + C.dates[i] + '</text>');
  svg.innerHTML = g + ligne(C.m200, '#9a9ea6', 1.5) + ligne(C.m50, '#e0a800', 1.5) + ligne(C.cours, 'var(--accent)', 2) + '<line id="curseur" y1="' + m.h + '" y2="' + (H - m.b) + '" stroke="var(--muted)" stroke-dasharray="3,3" style="display:none"/>';
  const bulle = document.getElementById('bulle'), cur = document.getElementById('curseur');
  svg.onpointermove = ev => {{ const r = svg.getBoundingClientRect(), i = Math.max(0, Math.min(n - 1, Math.round((ev.clientX - r.left - m.g) / (W - m.g - m.d) * (n - 1))));
    cur.setAttribute('x1', X(i)); cur.setAttribute('x2', X(i)); cur.style.display = '';
    bulle.style.display = 'block'; bulle.innerHTML = '<b>' + C.dates[i] + '</b><br>Cours : ' + C.cours[i] + (C.m200[i] ? '<br>Moyenne 200 j : ' + C.m200[i] : '');
    bulle.style.left = Math.min(X(i) + 10, W - 150) + 'px'; bulle.style.top = '10px'; }};
  svg.onpointerleave = () => {{ bulle.style.display = 'none'; cur.style.display = 'none'; }};
}}
dessiner(); addEventListener('resize', dessiner);
</script>"""


def fiche(r, extra=None, maintenant=None):
    """Page détaillée d'un titre. extra : {bilan: [...], actionnaires: [...], evenements: [...], historique: [...]}."""
    extra = extra or {}
    maintenant = maintenant or dt.datetime.now().strftime("%d/%m/%Y à %H:%M")
    li = lambda xs: "".join(f"<li>{E(x)}</li>" for x in xs)
    bilan = extra.get("bilan") or []
    t_bilan = ""
    if bilan:
        t_bilan = "<h3>📒 Le bilan sur plusieurs années</h3><div class='tableau'><table><tr><th>Année</th><th>Chiffre d'affaires</th><th>Bénéfice net</th><th>Argent généré après investissements</th></tr>" + "".join(
            f"<tr><td>{E(str(b['annee']))}</td><td>{nombre(b.get('ca'), 0)}</td><td>{nombre(b.get('benefice'), 0)}</td><td>{nombre(b.get('fcf'), 0)}</td></tr>" for b in bilan) + \
            f"</table></div><p class='petit'>Montants en {E(r.get('devise', ''))}, en millions.</p>"
    act = extra.get("actionnaires") or []
    t_act = ("<h3>🏦 Principaux investisseurs institutionnels</h3><ul>" + "".join(f"<li>{E(a['nom'])} : {a['part']:.1%}</li>" for a in act) + "</ul>") if act else ""
    ev = extra.get("evenements") or []
    t_ev = ("<h3>📅 Prochains événements</h3><ul>" + "".join(f"<li><b>{dt.date.fromisoformat(e['date']).strftime('%d/%m/%Y')}</b> : {E(e['texte'])}</li>" for e in ev) + "</ul>") if ev else ""
    hist = extra.get("historique") or []
    t_hist = ("<h3>🕓 Historique des signaux</h3><div class='tableau'><table><tr><th>Date</th><th>Cours</th><th>Court terme</th><th>Long terme</th></tr>" + "".join(
        f"<tr><td>{E(h['date'])}</td><td>{nombre(h['prix'])}</td><td>{badge(h['signal_ct'], True)}</td><td>{badge(h['signal_lt'], True)}</td></tr>" for h in hist[-20:][::-1]) + "</table></div>") if hist else ""
    infos = []
    if r.get("pea"):
        infos.append(f"Enveloppe : {r['pea']}")
    if r.get("dividende"):
        infos.append(f"Dividende : environ {r['dividende']:.1%} par an")
    if r.get("avis_analystes"):
        infos.append(r["avis_analystes"])
    if r.get("pct_institutions"):
        infos.append(f"Détenu à {r['pct_institutions']:.0%} par des investisseurs professionnels")
    if r.get("fonds_acheteurs"):
        infos.append("Acheté récemment par : " + ", ".join(r["fonds_acheteurs"]))
    resume = f"<h3>🏢 L'activité</h3><p style='font-size:14px'>{E(r['resume'])}…</p><p class='petit'>Description fournie en anglais par la source.</p>" if r.get("resume") else ""
    site = f"<p><a href='{E(r['site_web'])}' target='_blank' rel='noopener'>Site officiel →</a></p>" if r.get("site_web") else ""
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(r['nom'])} · SignalBourse</title><style>{CSS}</style></head><body>
<header><p><a href="../index.html">← Retour au tableau de bord</a></p><h1>{E(r['nom'])}</h1>
<p class="petit">{E(r['ticker'])} · {E(r.get('pays') or r.get('pays_siege') or '')} · {E(r.get('secteur') or r.get('theme') or r['type'])} · mis à jour le {maintenant}</p></header>
<main>
<div class="kpis">
 <div class="kpi"><div class="petit">Cours</div><div class="gros">{nombre(r['prix'])} <small>{E(r.get('devise', ''))}</small></div><div class="petit">{perfs(r)}</div></div>
 <div class="kpi"><div class="petit">Court terme (jours / semaines)</div>{badge(r['signal_ct'])}<div class="petit">{E(EXPLICATION_SIGNAL.get(r['signal_ct'], ''))}</div></div>
 <div class="kpi"><div class="petit">Long terme (mois / années)</div>{badge(r['signal_lt'])}<div class="petit">{E(EXPLICATION_SIGNAL.get(r['signal_lt'], ''))}</div></div>
 <div class="kpi"><div class="petit">Potentiel · risque</div><div class="etoiles" style="font-size:20px">{etoiles(r.get('score_pepite', 0))}</div><div class="petit">Risque {risque(r.get('vol_annuelle'))} · pire baisse sur 1 an {r.get('max_dd_1an', 0):.0%}</div></div>
</div>
<h3>📈 Les 2 dernières années</h3><div class="encart">{graphique(r.get('courbe'))}</div>
{'' if r['type'] == 'Forex' else f'<div class="encart" style="margin-top:12px">🛡️ <b>Seuil de protection</b> : {nombre(r["stop"])} (vendre si le cours passe en dessous, pour limiter la perte) · 🎯 <b>Objectif</b> : {nombre(r["objectif"])}</div>'}
<div class="deux">
 <div class="encart"><h3>🚀 Pourquoi ce potentiel</h3><ul>{li(r.get('raisons_pepite', []))}</ul></div>
 <div class="encart"><h3>🏥 La santé de l'entreprise</h3><ul>{li(r.get('raisons_fond', []))}</ul></div>
 <div class="encart"><h3>📉 L'évolution récente du cours</h3><ul>{li(r.get('raisons_tech', []))}</ul></div>
 <div class="encart"><h3>ℹ️ Bon à savoir</h3><ul>{li(infos)}</ul><p class="petit">{E(r.get('dirigeants', {}).get('texte', ''))}</p></div>
</div>
{t_bilan}{t_act}{t_ev}
<h3>📰 Actualités</h3><div class="encart" style="font-size:13px"><b>Plutôt positives</b><br>{liens(r.get('news_pos'))}<br><br><b>Plutôt négatives</b><br>{liens(r.get('news_neg'))}<br><br><b>Décisions des dirigeants</b><br>{liens(r.get('news_dirig'))}</div>
{t_hist}{resume}{site}
<div class="avert" style="margin-top:20px">Outil d'aide à la décision, pas un conseil en investissement.</div>
</main></body></html>"""


# ----------------------------------------------------------------------------
# Appli sur téléphone (icône, plein écran)
# ----------------------------------------------------------------------------

MANIFEST = {"name": "SignalBourse", "short_name": "SignalBourse", "start_url": "./index.html", "display": "standalone",
            "background_color": "#121316", "theme_color": "#0b57d0", "lang": "fr",
            "icons": [{"src": "icone-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}
SERVICE_WORKER = """const CACHE='signalbourse-v1';
self.addEventListener('install',e=>{self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(self.clients.claim());});
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(e.request,c));return r;}).catch(()=>caches.match(e.request)));
});"""


def icone(chemin, taille):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (taille, taille), "#0b57d0")
    d = ImageDraw.Draw(im)
    s = taille / 512
    pts = [(90, 380), (190, 270), (260, 320), (420, 140)]
    d.line([(x * s, y * s) for x, y in pts], fill="white", width=int(38 * s), joint="curve")
    d.polygon([(x * s, y * s) for x, y in [(440, 115), (440, 215), (345, 150)]], fill="white")
    im.save(chemin)
