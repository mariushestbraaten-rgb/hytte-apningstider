# Åpningstider fra ut.no til dnt.no

Henter åpningstidene til hyttene i `hytter.json` fra ut.no hver time og publiserer én liten side per hytte på GitHub Pages. Siden limes inn på dnt.no som iframe. Åpningstidene oppdateres bare på ut.no, dnt.no følger etter automatisk innen en time.

## Slik settes det opp (én gang)

1. Opprett et offentlig repo i GitHub-organisasjonen, for eksempel `hytte-apningstider`, og last opp alle filene herfra (også mappa `.github`).
2. Gå til **Settings → Pages** og velg **GitHub Actions** under *Source*.
3. Gå til **Actions**, velg «Oppdater åpningstider fra ut.no» og trykk **Run workflow**.
4. Etter et par minutter ligger siden på `https://<organisasjon>.github.io/hytte-apningstider/iungsdalshytta/`.
5. Åpne `.../test-innliming.html` for å se hvordan den ser ut inne i en artikkel.

## Kode til Optimizely

Lim inn i en HTML- eller embed-blokk. Bytt ut `<organisasjon>`.

**Med automatisk høyde (anbefalt, krever at blokken tillater script):**

```html
<iframe src="https://<organisasjon>.github.io/hytte-apningstider/iungsdalshytta/"
        title="Åpningstider for Iungsdalshytta"
        style="width:100%;height:680px;border:0;display:block" loading="lazy"
        data-apningstider></iframe>
<script>
  window.addEventListener("message", function (e) {
    if (!e.data || e.data.type !== "dnt-apningstider-hoyde") return;
    document.querySelectorAll("iframe[data-apningstider]").forEach(function (f) {
      if (f.contentWindow === e.source) f.style.height = e.data.hoyde + "px";
    });
  });
</script>
```

**Bare iframe (hvis script ikke er lov):** bruk iframen alene. Med dagens data trenger Iungsdalshytta ca. 590 px på pc og 800 px på mobil. Sett `height:800px` så ingenting kuttes, eller `600px` og godta at mobilbrukere scroller inne i boksen.

## Legge til flere hytter

Legg til en linje i `hytter.json` med ut.no-id (tallet i ut.no-lenken) og ønsket adresse:

```json
[
  { "id": 10973, "slug": "iungsdalshytta" },
  { "id": 10604, "slug": "gjendesheim" }
]
```

## Innstillinger i `bygg.py`

- `TREKK_FRA_EN_DAG`: ut.no lagrer sluttdato lik startdatoen til neste periode, og viser datoene slik selv. Står den på `False` (standard), viser iframen det samme som ut.no.
- `MANEDER_FREMOVER`: hvor langt frem sesongstripa og lista går (standard 12).

## Godt å vite

- **Feil hos ut.no:** Feiler hentingen, publiseres ingenting, og forrige versjon blir liggende. GitHub sender e-post til den som eier repoet når en kjøring feiler.
- **Pause etter 60 dager:** GitHub skrur av timeplanlagte kjøringer i repoer uten aktivitet på 60 dager, og varsler på e-post først. Trykk *Enable workflow* under Actions, eller gjør en liten endring i repoet.
- **Udokumentert API:** `ut.no/api/graphql` er endepunktet ut.no-nettsiden selv bruker. Det kan endres uten varsel. Avklar bruken med DNT sentralt.
- **SEO:** Sidene på GitHub har `noindex`, så de konkurrerer ikke med dnt.no i søk. Teksten i iframen regnes heller ikke som innhold på dnt.no-siden.
- **Font:** ABC Social brukes hvis den finnes på maskinen, ellers systemfonten. Webfonten er ikke lagt ved, fordi lisensen sannsynligvis ikke dekker GitHub Pages.

## Teste lokalt

```bash
python bygg.py                     # bygger til site/
python bygg.py --idag 2027-03-10   # bygger som om det var en annen dato
python -m http.server -d site      # åpne http://localhost:8000/test-innliming.html
```
