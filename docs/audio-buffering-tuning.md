# Automatische bufferingvergelijking

`tools/tune-audio-buffering.py` automatiseert een begrensde vergelijking op 48 kHz / 128 samples. Het onderzoekt de bestaande instellingen en playback `api.alsa.headroom` van 0, 32, 64, 96, 128, 192 en 256 frames. Dit is echte playbackbuffermarge in de PipeWire ALSA-backend, geen wijziging van de latencycorrectietabel of de kernel-USB-pakketplanning. Headroom wordt alleen tijdelijk op de Eleven Rack-outputnode toegepast.

Plan tonen:

```sh
python3 tools/tune-audio-buffering.py --output build/latency/buffering-tuning
```

Fysiek uitvoeren, met Main Out L → Line In L aangesloten en REAPER gesloten:

```sh
python3 tools/tune-audio-buffering.py --output build/latency/buffering-tuning --execute
```

Iedere kandidaat wordt eerst met één minuut van elk signaal getest. Alleen foutloze kandidaten met gemeten roundtriplatency tussen 10 en 12 ms gaan door naar twee verse-startcycli van 5, 15 en 30 minuten per signaal. Kandidaten dichter bij 12 ms krijgen voorrang. Het resultaat is een voorstel in `tuning.json`, geen automatisch geïnstalleerde standaard. Zonder bevestigde kandidaat blijven de defaults behouden. De fysieke afstelling is nog niet uitgevoerd.

De latency wordt bepaald uit de mediane fysieke lag van de betrouwbare witte-/roze-ruisvensters, niet uit sinus of enkel de gerapporteerde latency. De beperkingen van de regressiedetector blijven gelden; controleer verdachte audio. Deze begrensde headroomreeks garandeert niet dat het doel haalbaar is. Een eventuele aanbeveling betreft alleen het geteste profiel en systeem; andere profielen moeten daarna opnieuw gecontroleerd worden.

De tool gebruikt hetzelfde lock als de nachtrunner, zodat beide geen instellingen tegelijk aanpassen. Hij weigert te starten zolang de huidige regressiereeks actief is. Hij is niet aan de cronjob toegevoegd en heeft geen tijdvenster: bevestigingstests kunnen ruim vijf uur per kandidaat duren. De nachtelijke baselinemetingen blijven ongewijzigd. Iedere matrix herstelt de oorspronkelijke audio-instellingen; bij mislukte restauratie stopt de afstelling.
