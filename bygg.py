#!/usr/bin/env python3
"""Henter åpningstider fra ut.no og bygger én statisk side per hytte for innliming som iframe på dnt.no.

Kjøres av GitHub Actions hver time. Kan også kjøres lokalt:

    python bygg.py            bygger alle hyttene i hytter.json til mappa site/
    python bygg.py --idag 2027-03-01   bygger som om det var en annen dato (for testing)

Feiler henting fra ut.no for én hytte, avslutter scriptet med kode 1 uten å publisere.
Da blir forrige versjon liggende ute, så besøkende ser aldri en tom eller ødelagt boks.
Bare Python 3.9+ uten ekstra pakker.
"""

import argparse
import html
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from string import Template
from zoneinfo import ZoneInfo

ENDPOINT = "https://ut.no/api/graphql"
USER_AGENT = "dntoslo-apningstider/0.1 (+https://github.com/dntoslo)"
OSLO = ZoneInfo("Europe/Oslo")
ROT = Path(__file__).resolve().parent
UT = ROT / "site"

# ut.no lagrer sluttdato lik startdatoen til neste periode, og viser den slik på sin egen hytteside.
# Står den på False, viser vi datoene nøyaktig som ut.no. Sett True for å vise siste dag i perioden i stedet.
TREKK_FRA_EN_DAG = False

# Hvor mange måneder fremover sesongstripa og lista viser.
MANEDER_FREMOVER = 12

SPORRING = """
query($id: Int!) {
  cabin(id: $id) {
    id name bookingUrl updatedAt
    serviceStatusAll { serviceLevel beds from to openAllYear }
  }
}
"""

NIVA = {
    "STAFFED": ("Betjent", "betjent"),
    "SELF_SERVICE": ("Selvbetjent", "selvbetjent"),
    "NO_SERVICE": ("Ubetjent", "ubetjent"),
    "NO_SERVICE_NO_BEDS": ("Ubetjent uten senger", "ubetjent"),
    "FOOD_SERVICE": ("Servering", "annet"),
    "EMERGENCY_SHELTER": ("Nødbu", "annet"),
    "CLOSED": ("Stengt", "stengt"),
    "RENTAL": ("Utleie", "annet"),
    "UNKNOWN": ("Ukjent", "annet"),
}

MANEDER = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
           "august", "september", "oktober", "november", "desember"]
MND_KORT = ["jan", "feb", "mar", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "des"]


def hent(hytte_id):
    data = json.dumps({"query": SPORRING, "variables": {"id": hytte_id}}).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as svar:
            body = json.load(svar)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        raise RuntimeError(f"hytte {hytte_id}: fikk ikke svar fra ut.no ({e})") from e
    if body.get("errors"):
        raise RuntimeError(f"hytte {hytte_id}: GraphQL-feil fra ut.no: {body['errors']}")
    cabin = (body.get("data") or {}).get("cabin")
    if not cabin:
        raise RuntimeError(f"hytte {hytte_id}: finnes ikke på ut.no")
    return cabin


def dag(iso):
    return date.fromisoformat(iso[:10])


def perioder_fra(cabin, idag, slutt_vindu):
    ut = []
    for p in cabin.get("serviceStatusAll") or []:
        niva, klasse = NIVA.get(p.get("serviceLevel"), NIVA["UNKNOWN"])
        rad = {"niva": niva, "klasse": klasse, "senger": int(p.get("beds") or 0),
               "hele_aret": bool(p.get("openAllYear"))}
        if rad["hele_aret"]:
            ut.append(rad)
            continue
        if not p.get("from") or not p.get("to"):
            continue
        fra, til = dag(p["from"]), dag(p["to"])
        if til <= idag or fra >= slutt_vindu:
            continue
        rad.update(fra=fra, til=til)
        ut.append(rad)
    ut.sort(key=lambda r: r.get("fra", date.min))
    return ut


def vis_til(til):
    return til - timedelta(days=1) if TREKK_FRA_EN_DAG else til


def dato_lang(d, med_ar=False):
    tekst = f"{d.day}. {MANEDER[d.month - 1]}"
    return f"{tekst} {d.year}" if med_ar else tekst


def senger_tekst(n):
    return f"{n} senger" if n != 1 else "1 seng"


def bygg_innhold(cabin, idag):
    e = html.escape
    start_vindu = idag.replace(day=1)
    ar, mnd = divmod(start_vindu.month - 1 + MANEDER_FREMOVER, 12)
    slutt_vindu = date(start_vindu.year + ar, mnd + 1, 1)
    perioder = perioder_fra(cabin, idag, slutt_vindu)
    deler = []

    # Statusboks øverst
    hele = next((p for p in perioder if p["hele_aret"]), None)
    na = hele or next((p for p in perioder if p["fra"] <= idag < p["til"]), None)
    if na:
        detaljer = []
        if hele:
            detaljer.append("Hele året")
        else:
            detaljer.append(f"Til {dato_lang(vis_til(na['til']), na['til'].year != idag.year)}")
        if na["senger"]:
            detaljer.append(senger_tekst(na["senger"]))
        deler.append(
            f'<section class="na" aria-label="Status i dag">'
            f'<p class="na-status"><span class="prikk {na["klasse"]}" aria-hidden="true"></span>{e(na["niva"])} nå</p>'
            f'<p class="na-detalj">{e(", ".join(detaljer))}</p>')
    else:
        deler.append('<section class="na" aria-label="Status i dag">'
                     '<p class="na-status">Ingen registrert åpningstid i dag</p>')

    # Sesongstripe, bare for hytter med perioder
    if not hele and perioder:
        totalt = (slutt_vindu - start_vindu).days
        biter, peker = [], start_vindu
        for p in perioder:
            fra, til = max(p["fra"], start_vindu), min(p["til"], slutt_vindu)
            if fra > peker:
                biter.append(("ingen", (fra - peker).days))
            if til > fra:
                biter.append((p["klasse"], (til - max(fra, peker)).days))
            peker = max(peker, til)
        if peker < slutt_vindu:
            biter.append(("ingen", (slutt_vindu - peker).days))
        bar = "".join(f'<span class="{k}" style="width:{d / totalt * 100:.3f}%"></span>'
                      for k, d in biter if d > 0)
        idag_pos = max((idag - start_vindu).days / totalt * 100, 0.4)
        mnd_etiketter = []
        m = start_vindu
        while m < slutt_vindu:
            mnd_etiketter.append(f"<span>{MND_KORT[m.month - 1]}</span>")
            m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        deler.append(
            f'<div class="stripe" aria-hidden="true">'
            f'<div class="stripe-bar">{bar}</div>'
            f'<div class="stripe-idag" style="left:{idag_pos:.3f}%"></div>'
            f'<div class="stripe-mnd">{"".join(mnd_etiketter)}</div></div>')
    deler.append("</section>")

    # Liste over periodene, gruppert per år
    if hele:
        pass  # statusboksen sier alt
    elif perioder:
        deler.append('<div class="perioder">')
        gjeldende_ar = None
        for p in perioder:
            if p["fra"].year != gjeldende_ar:
                if gjeldende_ar is not None:
                    deler.append("</ul>")
                gjeldende_ar = p["fra"].year
                deler.append(f'<h2 class="ar">{gjeldende_ar}</h2><ul>')
            til = vis_til(p["til"])
            krysser = til.year != p["fra"].year
            datoer = f'{dato_lang(p["fra"])} til {dato_lang(til, krysser)}'
            gjelder = p["fra"] <= idag < p["til"]
            klasse_li = ' class="gjelder"' if gjelder else ""
            na_merke = ' <span class="na-merke">nå</span>' if gjelder else ""
            senger = f'<small>{senger_tekst(p["senger"])}</small>' if p["senger"] else ""
            deler.append(
                f'<li{klasse_li}>'
                f'<span class="prikk {p["klasse"]}" aria-hidden="true"></span>'
                f'<span class="datoer">{e(datoer)}{na_merke}</span>'
                f'<span class="niva">{e(p["niva"])}{senger}</span></li>')
        deler.append("</ul></div>")
    else:
        deler.append('<p class="tomt">Åpningstidene for neste sesong er ikke lagt inn ennå.</p>')

    # Bestilling og kilde
    hentet = datetime.now(OSLO)
    ut_lenke = f"https://ut.no/hytte/{cabin['id']}"
    bunn = ['<div class="bunn">']
    if cabin.get("bookingUrl"):
        bunn.append(f'<a class="knapp" href="{e(cabin["bookingUrl"])}" target="_blank" rel="noopener">Bestill overnatting</a>')
    bunn.append(f'<p class="kilde">Hentet fra <a href="{ut_lenke}" target="_blank" rel="noopener">ut.no</a> '
                f'{dato_lang(hentet.date(), True)} kl. {hentet:%H.%M}</p></div>')
    deler.append("".join(bunn))
    return "\n".join(deler), len(perioder)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--idag", type=date.fromisoformat, help="bygg som om dagens dato var denne (ÅÅÅÅ-MM-DD)")
    args = ap.parse_args()
    idag = args.idag or datetime.now(OSLO).date()

    hytter = json.loads((ROT / "hytter.json").read_text(encoding="utf-8"))
    mal = Template((ROT / "mal.html").read_text(encoding="utf-8"))
    UT.mkdir(exist_ok=True)
    (UT / ".nojekyll").write_text("")

    feil, oversikt = [], []
    for h in hytter:
        try:
            cabin = hent(h["id"])
        except RuntimeError as err:
            feil.append(str(err))
            continue
        innhold, antall = bygg_innhold(cabin, idag)
        mappe = UT / h["slug"]
        mappe.mkdir(parents=True, exist_ok=True)
        (mappe / "index.html").write_text(
            mal.substitute(navn=html.escape(cabin["name"]), innhold=innhold), encoding="utf-8")
        oversikt.append((h["slug"], cabin["name"], antall))
        print(f"OK  {cabin['name']} ({antall} perioder) -> site/{h['slug']}/")

    if feil:
        for f in feil:
            print(f"FEIL {f}", file=sys.stderr)
        sys.exit(1)

    (UT / "test-innliming.html").write_text((ROT / "test-innliming.html").read_text(encoding="utf-8"), encoding="utf-8")

    rader = "".join(f'<li><a href="{s}/">{html.escape(n)}</a> ({a} perioder)</li>' for s, n, a in oversikt)
    (UT / "index.html").write_text(
        '<!doctype html><html lang="nb"><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>Åpningstider fra ut.no</title><body style="font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto">'
        f'<h1>Åpningstider fra ut.no</h1><p>Sider for innliming på dnt.no.</p><ul>{rader}</ul></body></html>',
        encoding="utf-8")


if __name__ == "__main__":
    main()
