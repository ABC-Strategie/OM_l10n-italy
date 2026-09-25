# Imposta acquisti predefinita per fornitore

Modulo per **Odoo 19** (localizzazione IT).

## Cosa fa

Aggiunge sull'anagrafica del contatto un campo **"Imposta acquisti predefinita"**.

Quando si registra una **fattura fornitore** e si inserisce una riga **manuale
senza prodotto** (solo descrizione), l'imposta indicata sul fornitore viene
proposta in automatico sulla riga contabile, dopo essere stata rimappata dalla
**Posizione fiscale** del fornitore (se impostata).

## Perché, invece dell'imposta di default sul conto

L'imposta di default impostata sul *conto* si applica ogni volta che quel conto
viene usato, incluse le scritture di prima nota manuali (partita doppia), dove
aggiunge una riga d'imposta non voluta.

Legando invece il default al **fornitore**, l'imposta viene proposta **solo in
fattura fornitore** e **non** inquina le scritture manuali che usano gli stessi
conti.

## Uso

1. Anagrafica fornitore → scheda contabile:
   - **Posizione fiscale**: quella corretta (es. reverse charge UE / Extra-UE).
   - **Imposta acquisti predefinita**: es. `22% S IC` (oppure `22%`: con la
     posizione fiscale il risultato finale non cambia).
2. Registrando la fattura fornitore e aggiungendo una riga senza prodotto,
   l'imposta esce automaticamente.

## Nota tecnica per l'installazione (IMPORTANTE)

Il modulo estende il calcolo delle imposte di riga sovrascrivendo il metodo
`_compute_tax_ids` di `account.move.line`.

**Prima di installare in produzione, verificare sul sorgente esatto della
propria Odoo 19** che il campo `tax_ids` di `account.move.line` sia ancora
calcolato dal metodo `_compute_tax_ids`. Se in quella build il nome del compute
fosse diverso, adeguare di conseguenza il metodo in
`models/account_move_line.py` (l'aggancio logico non cambia).

Installare e **collaudare sempre prima in ambiente di staging**, mai a caldo in
produzione.

## Contenuto

```
partner_default_purchase_tax/
├── __init__.py
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   ├── res_partner.py
│   └── account_move_line.py
└── views/
    └── res_partner_views.xml
```

## Licenza

LGPL-3
