# Teststrategie

JS8Link gebruikt drie aanvullende testlagen. Elke laag heeft een eigen doel; dezelfde test hoeft
niet in alle lagen te worden gekopieerd.

## pytest: backend en API

pytest beschermt de domeinlogica, database en FastAPI-grens. Wijzigingen aan JS8Call-parsing,
berichtclassificatie, offsetkeuze, monitorberekeningen, migraties, authenticatie, configuratie of
API-responses horen hier een test te krijgen. De bestaande fixtures gebruiken een in-memory SQLite
database en een gesimuleerde JS8Call-client, zodat tests geen radio of netwerkdienst nodig hebben.

## Vitest: frontendlogica

Vitest is bedoeld voor deterministische frontendlogica die zonder browser kan draaien: formattering
van frequenties en offsets, UTC-tijdinterpretatie, sorteer- en filterfuncties, validatie en andere
herbruikbare helpers. Als logica moeilijk te testen is, verplaats die dan eerst uit `App.tsx` naar
een kleine module.

## Playwright: gebruikersflows

Playwright controleert de applicatie vanuit het perspectief van de gebruiker. De tests gebruiken
de lokale Vite-server en onderscheppen `/api/**`, zodat de radioverbinding voorspelbaar blijft.
Belangrijke flows zijn:

| Flow                | Wat wordt geborgd                                                            |
| ------------------- | ---------------------------------------------------------------------------- |
| Eerste configuratie | wizardstappen, API-test, applicatielogin en opslaan                          |
| Navigatie           | Chat, Berichten, Bandmonitor en Instellingen openen                          |
| Chat                | laatst gehoord station kiezen, nieuwe callsign invoeren en bericht verzenden |
| Offset              | vaste offset instellen en terugschakelen naar Auto                           |
| Monitor             | filters, tabbladen, historie en kaartweergave blijven beschikbaar            |
| Instellingen        | applicatie- en JS8Call-tab, taal en thema opslaan                            |
| Fouten              | begrijpelijke UI bij API- en verbindingsfouten                               |

Een bug die eerst in de browser wordt gevonden krijgt een Playwright-regressietest. Backend- en
frontendtests blijven daarnaast nodig om de oorzaak lokaal en snel te isoleren.

## Commando's

```text
just frontend-unit
just frontend-e2e
just test
```

Voor een nieuwe omgeving:

```text
cd frontend && npx playwright install chromium
```
