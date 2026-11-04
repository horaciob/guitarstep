# guitarr

Aprendé y practicá guitarra con la guitarra enchufada: te escucha y te dice qué
notas o acordes erraste, cuáles salteaste, cuáles sobraron y dónde te fuiste de
tiempo. La idea central: **todo se aprueba tocando**, y el que decide si salió es
el oído (y, si querés, la cámara).

- **Interfaz gráfica** (`guitarr gui`): ruta de aprendizaje, acordes, cifrados, herramientas, cámara, práctica en vivo, análisis de tomas, historial y progreso.
- **En vivo** (`guitarr live`): guitarra enchufada a la compu, feedback instantáneo. Modo *espera* (aprender) o *tempo* (metrónomo, con loop y entrenador de velocidad).
- **Toma grabada** (`guitarr file`): análisis más preciso de algo que ya grabaste.

## Instalación

```bash
python3.11 -m venv .venv                 # basic-pitch soporta hasta 3.11
.venv/bin/pip install -e ".[dev]"        # crea el comando `guitarr`
source .venv/bin/activate
```

Las versiones están fijas en `pyproject.toml` y `requirements.txt` (basic-pitch, librosa y numpy se rompen seguido entre versiones).

## Interfaz gráfica

```bash
guitarr gui          # abre http://127.0.0.1:8765 en el navegador
```

- **Practicar**: elegís canción, pista, compases y modo. Ves la tablatura (cuerda y traste) desplazándose, la nota actual, el nivel de entrada, la afinación y cada acierto o error. Al terminar te muestra el resultado por compás y un botón para practicar los compases más flojos con el entrenador.
- **Analizar toma**: transcribe una toma, la alinea con la referencia y dibuja un piano-roll de la referencia contra lo que tocaste.
- **Afinador**, **Historial** (progreso y compases flojos) y **Ajustes** (entrada, canal, salida del metrónomo, puerta de ruido, sensibilidad y calibración de latencia).
- Sin guitarra: "Cargar la demo" deja preparada una toma simulada con errores plantados.

**Aprender**
- **Inicio**: nivel y XP, racha de días (la semana a la vista), la siguiente lección, tus compases flojos y lo último que ganaste.
- **Ruta**: 5 niveles y 11 lecciones (de las cuerdas al aire a la cejilla y la pentatónica). Cada lección tiene la idea, consejos, diagramas y **ejercicios que se aprueban tocando**: notas sueltas, un acorde N veces, cambios entre acordes o un cifrado con metrónomo, cada uno con un puntaje mínimo.
- **Tutorías**: cada lección trae búsquedas de videos sugeridas y podés fijar tu video favorito (si es de YouTube, se ve ahí mismo).
- **Acordes**: diccionario de 39 acordes por familia (abiertos, séptimas, color, cejilla, quintas). Tocás cada cuerda del diagrama para escucharla y **Comprobar** te escucha rasguearlo y te dice qué nota faltó o sobró.
- **Cámara**: detecta tu mano (MediaPipe, todo local) y, con una calibración de 4 clics sobre el mástil, te dice qué dedos están en la cuerda y el traste correctos. Si mantenés la postura un segundo, después lo podés confirmar por oído.

**Tocar**
- **Cifrados**: acordes por compás para tocar con metrónomo. Te marca cada acorde que no entró o se fue de tiempo, y los rasguidos de relleno no cuentan como error. Trae 12 ejercicios y podés **escribir los tuyos** en un formato de texto simple (con vista previa en vivo).
- **Herramientas**: metrónomo con tap tempo; **minuto de cambio**, que cuenta solo los cambios que sonaron limpios y guarda tu récord por par de acordes; y diapasón con escalas y acordes resaltados.

**Progreso**: suman XP los ejercicios aprobados, las lecciones completas, los acordes dominados (por oído o cámara), los minutos de cambio y la práctica. Vive en `~/.guitarr/progreso.json` y lo comparten la web y la terminal.

El audio se procesa en Python (baja latencia); el navegador solo muestra el estado.

## En vivo (terminal)

```bash
guitarr devices                          # ver entradas; marca la que parece tu interfaz
guitarr config --device 3 --channel 1    # dejarla guardada
guitarr calibrate                        # medir la latencia una vez (se guarda)
guitarr tune                             # afinador

guitarr live cancion.gp5                                    # modo espera
guitarr live cancion.gp5 --mode tempo --speed 0.7           # metrónomo al 70%
guitarr live cancion.gp5 --start-bar 9 --end-bar 12 --trainer   # loop: sube 5% cada vuelta limpia
guitarr live cancion.gp5 --track lead --start-bar 9 --save-preset   # recordar opciones de esta canción
```

- Cada sesión se graba en `~/.guitarr/tomas/` y se registra en el historial.
- **Entrenador de velocidad** (`--trainer`): arranca al 60% (o `--speed`). Si la vuelta sale con al menos `--target` (90 por defecto), sube `--speed-step` (5%); si sale bastante peor, baja. Tope: `--max-speed`.
- **Legato**: también detecta hammer-ons, pull-offs y slides (notas sin ataque de púa). Se desactiva con `--no-legato`.
- **Acordes**: si te equivocás, te dice qué nota faltó o sobró ("faltó C# (3ra), sobró C").

Consejos:
- Con el nivel entre −30 y −10 dB está bien. Si dice "CLIPEA", bajá la ganancia.
- Conviene una señal limpia (sin distorsión) para la detección; los efectos los podés monitorear aparte.
- Usá auriculares para el metrónomo, así el click no se mete en la entrada.
- Si no detecta ataques suaves: `--sensitivity 1.5` o `--gate-db -60` (o desde Ajustes en la interfaz).

## Toma grabada

```bash
guitarr file cancion.mid mi_toma.wav
guitarr file guitarra.wav mi_toma.wav --bpm 120   # referencia en audio
guitarr file cancion.mp3 mi_toma.wav --separate   # aísla la guitarra (pip install -e ".[separate]")
```

Las transcripciones y separaciones quedan en caché (`~/.guitarr/cache`), así que la segunda vez es casi instantánea.

## Referencia

Lo mejor es **Guitar Pro** (`.gp3/.gp4/.gp5`) o un **MIDI exportado de una tab** (Guitar Pro, Songsterr, MuseScore).
Guitar Pro trae la cuerda y el traste reales; para MIDI y audio, la tablatura se estima intentando no mover mucho la mano.
Las repeticiones de Guitar Pro se leen como están escritas, sin desplegarlas.

```bash
guitarr tracks cancion.mid      # listar pistas
... --track 2                   # o --track "lead"
```

Otras opciones: `--transpose N` (afinación distinta), `--start-bar/--end-bar`,
`--bpm/--first-beat/--beats-per-bar` (si la grilla de compases sale corrida). Los cambios de compás del MIDI o del GP se respetan.

## Cifrados y progreso (terminal)

```bash
guitarr cancionero                                   # cifrados disponibles (incluidos y tuyos)
guitarr cancionero 03-pop-sol                        # ver uno, compás por compás
guitarr cancionero --formato                         # cómo escribir los tuyos (van en ~/.guitarr/cifrados/)
guitarr live --cifrado 03-pop-sol --mode tempo       # tocarlo con escucha
guitarr progreso                                     # nivel, XP, racha, lecciones y acordes dominados
```

Un cifrado es texto plano:

```
titulo: Pop en Sol
bpm: 90
rasgueo: D.DU.UDU
[Verso]
G | D | Em | C
G | D | C G | %
```

## Historial

```bash
guitarr history                 # canciones practicadas
guitarr history cancion         # evolución + tus 3 compases más flojos + comando sugerido para practicarlos
```

## Probar sin guitarra

```bash
guitarr demo                                         # genera demo/ con errores plantados
guitarr file demo/referencia.mid demo/toma.wav
guitarr live demo/referencia.mid --simulate demo/toma.wav --mode tempo --speed 0.9
```

## Tests

```bash
pytest           # ~15 s: grilla, MIDI/GP, alineación, demo, entrenador, cifrados (todos rasgueados), ejercicios, acordes por oído, minuto de cambio, progreso, API
```

## Datos

Todo vive en `~/.guitarr/` (se cambia con la variable `GUITARR_HOME`): `config.toml`, `progreso.json`, `cifrados/` (los tuyos), `canciones/`, `tomas/`, `historial/` y `cache/`.

El contenido para aprender está en `guitarr/data/`: `acordes.json`, `ruta.json` y `cifrados/*.txt`.

## Cómo funciona

- **file**: basic-pitch (audio a notas) + limpieza de armónicos y resonancias. Después, DTW + regresión local sobre los ataques para alinear tempos, y emparejado de notas con tolerancia adaptada a la densidad del pasaje.
- **live**: los ataques se detectan por spectral flux (púa) y por cambio de altura (legato). La altura sale de YIN, y los acordes de un cromagrama, con unos 110 ms de latencia; después pasa por el seguidor de partitura (espera o tempo). El metrónomo se sincroniza con la entrada usando los timestamps del ADC/DAC de CoreAudio.

- **Acordes con escucha**: un cifrado se convierte en rasguidos (las notas de cada cuerda, con capo). Cada rasguido se compara contra el acorde esperado por cromagrama:
  - Si falta una nota y suena otra en su lugar (por ejemplo mayor en vez de menor), es error.
  - Los armónicos de las cuerdas graves (5º, 7º, 9º, 11º) no se confunden con notas tocadas.
  - Medido con rasguidos sintetizados: 1 falso error cada 630 acordes bien tocados; detecta el 100% de los acordes equivocados y 2 de cada 3 cambios mayor/menor.
- **Cámara**: MediaPipe (copiado en `gui/static/vendor`, funciona sin internet). Con 4 puntos del mástil se arma una transformación bilineal, y la posición de cada yema se pasa a traste con el espaciado real de los trastes (regla del 12-TET).
- **Web**: módulos ES servidos tal cual por FastAPI (sin Node ni build).

Código: `guitarr/` (`core`, `reference`, `analysis`, `dsp`, `follow`, `session`, `audio_io`, `tuner`, `history`, `catalog`, `progress`, `config`, `cli`, `gui/`). La web: `gui/static/main.js` (router), `views/` (aprender y herramientas), `app.js` (práctica, análisis, afinador, historial, ajustes) y `lib/` (diagramas, sonido y escucha).
`listener.py` se mantiene como atajo: `python listener.py ...` equivale a `guitarr ...`.
