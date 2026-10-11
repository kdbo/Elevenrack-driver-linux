# Langdurige loopbackregressie

`tools/test-audio-regression.py` gebruikt de bestaande JACK/PipeWire-loopbacktool. Elk profiel krijgt een verse audiostart, vijf seconden stille opwarming en vervolgens sinus (997 Hz), deterministische witte of roze ruis. De standaardreeks omvat alle 24 samplefrequentie/buffercombinaties, drie signalen en 1, 5, 15 en 30 minuten per signaal. Dat is 61,2 uur signaal, plus opstarttijd. Hoge samplefrequenties met kleine buffers worden meegenomen om mogelijke fouten vast te leggen.

## Aansluiten en starten

Verbind tijdelijk **Main Out L met Line In L**. Gebruik geen microfooningang. Houd de analoge ingang schoon: geen effecten of verwerking in de loopbackroute. Sluit REAPER en andere audioprogramma's. De test stuurt ongeveer -30 dBFS piekniveau uit; controleer vooraf de fysieke routing en zet aangesloten luidsprekers zacht. De opname wordt nooit naar de uitgang teruggestuurd.

Een eerste gerichte test:

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-48k-128-1min --profiles 48000:128 --minutes 1
```

Daarna dezelfde combinatie langer testen:

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-48k-128-long --profiles 48000:128 --minutes 5 15 30
```

Alle combinaties en lengtes:

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-full
```

`--cycles 2` herhaalt de reeks. `--signals white pink` selecteert signalen. `--plan` toont de omvang zonder audio-instellingen te veranderen. `--seconds 10` is voor een korte technische controle.

De volledige reeks bewaart circa 122 GB aan opname- en referentieaudio, plus logs. Een enkele 30-minutenrun op 96 kHz gebruikt ongeveer 1,6 GB geheugen tijdens opname. Controleer vrije ruimte en geheugen vooraf. Analyse gebruikt geheugenmapping. Compiler, libjack, PipeWire/JACK-tools en de geïnstalleerde Eleven Rack-driver/backend zijn vereist; NumPy is niet nodig.

## Logboeken en beoordeling

Per run worden ruwe float32-audio, het referentiesignaal, callbacktijdstempels, gerapporteerde latency en passieve ALSA-status/hardwareparameters bewaard. `matrix.json` bevat resultaten per profiel; `regression.json` bevat het verloop van de reeks. `.regression.json` bevat analysevensters en gevonden afwijkingen. Falen van een profiel stopt de andere profielen niet; een fout bij instellen/starten stopt de reeks.

De analyse controleert gemelde opname-xruns, de daadwerkelijke graph-/ALSA-instellingen en herstarts van de PCM-streams. Een scan over het signaal na de eerste seconde zoekt niet-eindige/clippende samples en reeksen van minstens 64 vrijwel nul of identieke samples. Elke 100 ms wordt een venster van 512 samples gecorreleerd; onvoldoende overeenkomst (<0,80) en plotselinge delayverschuivingen (>1 ms, minstens acht samples) worden gemarkeerd. Sinus heeft een dubbelzinnige delay door periodiciteit en wordt daarom niet gebruikt om absolute delay of drift te bewijzen.

Deze eerste detector is een screening, geen garantie dat elke korte glitch gevonden wordt. Analoge filtering/ruis kan ook een correlatiefout veroorzaken. Beoordeel verdachte opnames voordat een driverregressie wordt vastgesteld. Opwarming-xruns blijven in het log, apart van opname-xruns. De test wijzigt geen correctietabel en stelt geen nieuwe buffering in de driver in.

Ctrl+C stopt de reeks. Het matrixscript herstelt in `finally` de eerdere hardwarefrequentie, PipeWire-instellingen en actieve audioservices. Bij kill -9, stroomuitval of een fout tijdens herstel geldt die garantie niet; `matrix.json` toont `restored`. De tijdelijke override is `~/.config/wireplumber/wireplumber.conf.d/99-eleven-matrix-rate.conf`. Bewaar logs van mislukte of afgebroken runs.

## Softwarecontrole zonder hardware

```sh
cc -shared -fPIC -O2 tools/latency-correlation.c -o build/latency/liblatency-correlation.so -lm
python3 tools/test-regression-analysis.py
```

Deze vier synthetische tests controleren een schoon vertraagd signaal, stilte, een xrun en een plotselinge delayverschuiving. Langdurige fysieke regressieruns moeten nog uitgevoerd worden; het bouwen van deze tools levert daarvoor nog geen stabiliteitsresultaat op.

## Automatisch 's nachts

De geïnstalleerde gebruikerscronjob start dagelijks om 23:00, Europe/Brussels. `run-nightly-regression.py` verwerkt een blijvende wachtrij: alle 24 profielen, drie signalen en vier lengtes. Elke taak is één combinatie/signaal/testlengte. De volgende nacht wordt verdergegaan bij de volgende onafgewerkte taak. Een volledig uitgevoerde maar gefaalde audiotest wordt bewaard en de wachtrij gaat verder; een onvolledige taak wordt de volgende nacht opnieuw geprobeerd. Na voltooiing van alle 288 taken doet de cronjob geen nieuwe audiotests.

Een nieuwe taak begint alleen als de verwachte looptijd plus twee minuten reserve in het venster past. Om 03:55 wordt een eventueel uitgelopen taak gestopt met tijd voor audioherstel vóór 04:00. Bij een vastgelopen proces kan geforceerd stoppen nodig zijn; controleer dan het herstelrapport. Open REAPER, onvoldoende schijfruimte (<8 GiB) of een andere actieve nachtrun verhindert starten. Dit detecteert niet elk ander audioprogramma.

Laat de computer wakker, de gebruikersaudiosessie beschikbaar en de Eleven Rack aanstaan, met Main Out L → Line In L aangesloten. Cron wekt een slapende computer niet. Schakel automatische slaap vooraf uit voor de testnachten. De tests onderbreken normaal audiogebruik.

Voortgang: `build/latency/nightly-regression/queue.json`. Hoofdlog: `build/latency/nightly-regression/cron.log`; iedere taak heeft ook een eigen log en resultaatmap.

De cronjob is herkenbaar aan `# eleven-rack-nightly-regression`. Verwijder die regel via `crontab -e` om toekomstige nachtruns uit te schakelen. Dit stopt een al actieve run niet.

## Extra multitoontest

De apart selecteerbare `multitone` combineert 431, 997, 1871 en 2973 Hz met gelijke amplitude. De som wordt door vier gedeeld, zodat het bestaande maximale uitgangsniveau behouden blijft. Het gecombineerde patroon herhaalt zich na één seconde; de latencyzoekrange blijft onder 200 ms. De analyse gebruikt hiervoor vensters van 100 ms om de frequentiecombinatie te herkennen. Dit geeft meer informatie dan een enkele sinus, maar analoge faseverschuiving/filtering kan de gevonden piek en overeenkomst nog beïnvloeden.

```sh
python3 tools/test-audio-regression.py --output build/latency/regression-multitone --profiles 48000:128 --minutes 1 --signals multitone
```

Start deze aparte run pas wanneer de huidige runner is afgelopen: `test-audio-regression.py` zelf neemt het nachtelijke lock niet over. De bestaande nachtelijke wachtrij blijft 288 taken met sinus/witte/roze ruis en wordt niet aangepast. Twee extra synthetische tests controleren absolute multitoondelay (ook >100 ms) en een delayverschuiving. Fysieke multitoonmetingen zijn nog niet uitgevoerd. De multitoontest heeft geen afzonderlijke detector per frequentie voor fase- of amplitudesprongen; hij gebruikt de gezamenlijke correlatie en de bestaande signaalscan.
