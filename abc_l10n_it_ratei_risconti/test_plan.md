# Piano di collaudo - ABC Ratei e risconti

D = 31/12/2025 (ISAP) salvo il caso 8 (GEAPLAST, D = 30/06/2026). Lo storno è sempre l'inverso in D + 1.

| # | Caso | Dati | Atteso in D |
|---|------|------|-------------|
| 1 | Risconto attivo | Assicurazione 1.200,00, fattura 01/10/2025, competenza 01/10/2025–30/09/2026 | Dare Risconti attivi 897,53 / Avere Assicurazioni |
| 2 | Rateo passivo da riga dell'anno dopo | Bolletta registrata 15/02/2026, 300,00, competenza 01/11/2025–31/01/2026 | Dare Spese telefoniche 198,91 / Avere Ratei passivi |
| 3 | Rateo passivo da scheda | Interessi stimati 1.810,00, 01/12/2025–31/05/2026 | Dare Interessi passivi 308,30 / Avere Ratei passivi |
| 4 | Risconto passivo | Vendita 01/12/2025, 2.400,00, 01/12/2025–30/11/2026 | Dare Ricavi 2.196,16 / Avere Risconti passivi |
| 5 | Rateo attivo | Interessi attivi registrati 31/03/2026, 450,00, 01/10/2025–31/03/2026 | Dare Ratei attivi 227,47 / Avere Interessi attivi |
| 6 | Leasing pluriennale | Maxicanone 12.000,00, 01/07/2025–30/06/2030 | Dare Risconti attivi 2.398,69 + Dare Risconti pluriennali 8.392,11 / Avere Canoni 10.790,80 |
| 6-bis | Quota fiscale | Periodo fiscale 01/07/2025–31/12/2027 | Report leasing: fiscale 2.415,75, civilistica 1.209,20, differenza 1.206,55 |
| 7 | Nota di credito | NC 200,00 stesse date del caso 1 | Dare Assicurazioni 149,59 / Avere Risconti attivi |
| 8 | Esercizio non solare | Assicurazione crediti 3.650,00, 01/04/2026–31/03/2027 | Al 30/06/2026: Dare Risconti attivi 2.740,00 |
| 9 | Pregresso | Canone 6.000,00, 01/07/2024–30/06/2026, riscontato 4.487,67 al 31/12/2024 | Storno 01/01/2025 4.487,67; al 31/12/2025 risconto 1.487,67 |
| 10 | Avviso | Riga del caso 1 non elaborata, data di blocco 31/12/2025 | Solo avviso, data salvata |
| 11 | Integrativa | Fattura 10/03/2026, 620,00, 01/12/2025–31/01/2026 | Nuova elaborazione con la sola riga: Ratei passivi 310,00 |

## Passi sullo stage

1. Installare il modulo; verificare in Impostazioni che i metodi nativi siano "manuale" e i menu nativi nascosti.
2. Configurare registro e conti; creare le eccezioni necessarie (GEAPLAST: ratei passivi per natura).
3. Registrare i casi 1–9 e 11 con le date di competenza sulle righe (o come schede per 3 e 9).
4. *Ratei e risconti › Elabora* al 31/12/2025: controllare l'anteprima, confermare, verificare scrittura e storno.
5. Stampare il prospetto; aprire *Pluriennali, leasing e quadratura* nelle tre modalità.
6. Registrare il caso 11 e rilanciare *Elabora*: deve nascere un'integrativa con la sola riga nuova.
7. Annullare l'elaborazione integrativa e poi la principale: le scritture devono risultare annullate.
