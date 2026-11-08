# guitarr — roadmap

Ideas for what to build next: lessons, theory, jazz, practice tools, tone, and interface and usability.
Every item follows the rules in `CLAUDE.md`. The listener grades the clean signal. Decisions live on the
server. Every string is in `en.json` and `es.json`. Color always comes with a word or a number. Gear names are generic.

## Ground rules for this plan

- **Our own work.** Every item is built from scratch, with our own text, examples, exercises, data and code.
  We take inspiration from ideas and interaction patterns. We don't copy lesson text, images, tabs, code or
  data files.
- **No copyrighted music.** Etudes, licks and progressions are original or generic (a ii–V–I, a 12-bar
  blues). No lyrics, no note-for-note transcriptions of recorded solos.
- **Generic gear.** Effects and amps are described by what they do ("mid-hump overdrive", "4-stage phaser"),
  never by brand or model.
- **Third-party notices.** If we ever reuse a third-party file verbatim, its license goes into
  `THIRD_PARTY_NOTICES.md` in the same commit. The plan assumes we don't.

Sizes: **S** ≈ an afternoon, **M** ≈ a few days, **L** ≈ a week or more.

---

## A. Theory foundations (course content) — ✅ done

1. **Parts of the guitar and reading tab** (S). A first lesson on the parts of the guitar, string numbers,
   and how to read tab (lines = strings, numbers = frets). It ends with a short "play what the tab says"
   exercise.
2. **Sharps and flats on a piano keyboard** (S). A small keyboard drawing explains half steps and
   enharmonics (C♯ = D♭) before mapping them onto one string.
3. **Intervals by counting frets** (M). Name intervals by semitones on one string, then across strings.
   A lesson with a fretboard diagram and listener-graded "play the interval" exercises.
4. **Interval ear trainer** (M). The app plays two notes and you choose the interval. Then you play the
   second note and the listener checks it. Understanding and playing are scored separately (see D4).
5. **Find the note** (S). A random note name and a string: play it. The listener grades it. The pool grows
   by string and fret range.
6. **Fretboard degree map** (M). A movable map of scale degrees (1, ♭3, 5…) relative to any key, as an
   alternative to note names. The label toggle cycles notes → degrees → none.
7. **Building the major scale** (S). The W-W-H-W-W-W-H formula, degrees, and one octave on one string,
   then in one position.
8. **The major scale in all 12 keys, spelled correctly** (M). A spelling engine (F♯ major has E♯, G♭ major
   has C♭) in Python, used by every scale and chord view.
9. **Natural minor and the relative minor** (S). Same notes, different home. Includes a "which one is it?"
   listening drill.
10. **Major scale positions across the neck** (M). Five connected positions chosen by fret range. Each
    exercise is pinned to one range.
11. **Three-notes-per-string patterns** (M). An alternative fingering with alternate-picking exercises at
    rising tempos.
12. **Major vs minor pentatonic: one shape, two homes** (S). Show that the same box is A minor and C major
    pentatonic.
13. **Harmonic and melodic minor** (M). The raised 7th (and 6th), with a short original melody per scale.
14. **The modes as color notes** (L). Dorian (natural 6), Mixolydian (♭7), Lydian (♯4), Phrygian (♭2) and
    Locrian. Each over a drone, with its characteristic note highlighted.
15. **Symmetric scales** (M). Whole-tone, half-whole and whole-half diminished. Patterns repeat every 2 or
    3 frets.
16. **Bebop scales** (M). The dominant and major bebop scales: the added passing tone keeps chord tones on
    the beat.
17. **The altered scale** (M). The 7th mode of melodic minor over a dominant chord, shown as "♭9 ♯9 3 ♯11 ♭13 ♭7".

## B. Chords and harmony — ✅ done

18. **Build a triad by clicking** (M). Choose the root, 3rd and 5th on the fretboard to build a major or
    minor triad. You get immediate feedback, then play it.
19. **Triad inversions on string sets** (M). Root position, 1st and 2nd inversion on the 1-2-3, 2-3-4 and
    3-4-5 string sets, with slash names (C/E, C/G).
20. **Inversions for smooth bass lines** (S). Turn C–Em–F–G into C–Em/B–F/A–G so the bass walks down. Uses
    an original chart.
21. **Sus2, sus4 and sixth chords** (S). How they're built, what they're for, and charts that use them.
22. **The seventh-chord family** (M). maj7, 7, m7, m7♭5, dim7 and m(maj7): their formulas, one shape per
    string set, and the listener grading each one.
23. **Diatonic harmony with roman numerals** (M). Harmonize the major scale in triads (I ii iii IV V vi
    vii°). Charts can show chords as numerals or names.
24. **Harmonizing in sevenths and ninths** (M). The same, stacking more thirds. Degree labels on every
    chord tone.
25. **Seventh chords in minor keys** (S). Natural and harmonic minor, and why V becomes dominant.
26. **Chord finder** (L). Choose a root and quality to see every voicing on the neck, filtered by fret range
    and string set.
27. **Name that chord** (M). Fret notes on a clickable neck and get the chord name back (reverse lookup).
    This lives in the chords view.
28. **Drop-2 voicings** (M). maj7, 7, m7 and m7♭5 on the top four and middle four strings, with all
    inversions.
29. **Drop-3 voicings** (M). With the bass on the 6th or 5th string. The comping set for jazz chord-melody.
30. **Shell voicings** (S). 1-3-7 and 1-7-3 on the low strings. The first jazz comping lesson.
31. **Extensions and altered dominants** (M). 9, 11, 13, ♭9, ♯9, ♯11 and ♭13, with what each one sounds
    like and a playable shape for each.
32. **Voice-leading engine** (L). Given a progression, choose the inversion of each chord closest to the
    previous one, by top note or bass note. It produces charts and exercises automatically.
33. **Guide-tone lines** (M). 3rds and 7ths through a ii–V–I as a two-note line, played alone and then over
    a backing.

## C. Jazz curriculum (new levels) — ✅ done

34. **Level "Jazz foundations": the major ii–V–I** (M). Shell voicings in 12 keys, a chart per key, and
    graded changes.
35. **The minor ii–V–i** (M). m7♭5 – 7♭9 – m6, with drop-2 and shell options.
36. **Jazz blues in F** (M). Twelve bars with ii–V turnarounds and a secondary dominant. An original head
    and a comping chart.
37. **Turnarounds** (S). I–vi–ii–V, iii–VI–ii–V and the tritone-substituted versions, as loops.
38. **Tritone substitution** (S). Why D♭7 can replace G7 (shared 3rd and 7th), shown with guide tones.
39. **The I–vi–ii–V "song form" loop** (S). A generic 32-bar AABA form built on standard turnarounds, not on
    any specific tune.
40. **Comping rhythms** (M). Four-to-the-bar quarter notes, the "Charleston" figure, anticipations and
    space. The strum format gets ties and swing.
41. **Walking bass on guitar** (M). Root on beat 1, chord tones and passing tones, and a chromatic approach
    into the next root.
42. **Arpeggios over the changes** (M). Generated chord-tone arpeggios for every chord of a progression,
    kept in one fret range.
43. **Approach notes** (M). Chromatic from below and diatonic from above into a chord tone. Generated licks
    per chord.
44. **Enclosures** (M). Above + below → target, aimed at the root, 3rd or 7th. Exercises generated from any
    progression.
45. **Eighth-note lines from a chord tone** (M). Eight notes per chord starting on the root, 3rd or 7th,
    ascending or descending, with enclosure variants.
46. **Swing feel** (S). A swing ratio for the metronome, the chart playback and the listener's timing window
    (straight / light / hard).
47. **Original jazz etudes** (L). Short pieces written by us over standard progressions, one per level, as
    lick exercises plus a chart.
48. **Advanced ear stretch: tone rows** (S, optional). Hear and play 12-note rows that use every pitch
    once, as a chromatic reading and ear challenge.

## D. Teaching method and learning flow — ✅ done

49. **Five-step lesson flow** (M). Discover → understand → guided practice → independent practice →
    vary and apply. A small step indicator in every lesson.
50. **Fading guidance** (M). The same exercise at a higher stage hides labels (degrees on → note names
    only → none), so you rely on the sound and the neck.
51. **Variation checks** (M). After you pass, the exercise comes back in another key or fret range, to
    check you learned the relationship and not a picture.
52. **"Understood" vs "played" progress** (S). Quizzes and the listener are scored and shown separately.
    The app never mixes a self-rating with a verified result.
53. **Test out of a lesson** (M). A short check lets you skip what you already know, with the result
    recorded on the server.
54. **Spaced review queue** (L). Passed exercises come back on growing intervals. The home page shows
    "review today". The schedule is computed in Python.
55. **Per-section song progress** (M). Each section of a song moves through not started → learning →
    unsure → solid → ready, each with a target BPM. Mastery is the average of the sections.
56. **Speed trainer** (M). After a clean pass, raise the tempo by N% up to a target, and step back after
    two misses.
57. **Loop a section with count-in** (S). Choose bars in any chart to loop them, with a count-in on every
    pass.
58. **Level recap** (S). The last lesson of every level is a mixed review of its exercises.
59. **Concept dialogs** (S). "What's a 3rd?" opens in a `<dialog>` without leaving the exercise. The same
    glossary text is reused across lessons.
60. **Hints with levels** (S). In practice, a hint first shows the string, then the fret, then the note.
    How many hints you used is recorded with the result.

## E. Practice tools — ✅ done

61. **Random practice box** (S). Random key, chord, scale or position, with a "lock" on any field. For
    warm-ups and drills.
62. **Rhythm test** (M). Strum on the beat for N bars. The listener measures how early or late each onset
    is, and shows a timing histogram with numbers.
63. **Metronome upgrades** (M). Accent patterns, subdivisions, a count-in toggle, swing, and a "silent
    bar" mode (click 3 bars, drop 1) for inner time.
64. **Chord-quality ear trainer** (M). Major / minor / 7 / maj7 / m7 / m7♭5 by ear, with the shapes
    revealed after you answer.
65. **Melodic echo** (M). The app plays a short original phrase and you play it back. The listener grades
    the pitches and the rhythm.
66. **Strumming-pattern library** (S). Named 3/4 and 4/4 patterns as strum presets for charts, each with a
    one-bar exercise.
67. **Scale-over-chord explorer** (M). Choose a chord and a scale to see chord tones and tensions with
    degree labels (not color alone) on the fretboard explorer.
68. **Practice heatmap and tempo curve** (M). A 12-month consistency grid, a minutes number in each cell's
    tooltip, and a BPM-over-time line per exercise.
69. **Time-budget plans** (S). Choose 15 / 30 / 60 / 120 minutes and the server fills today's plan from
    review items, the next lesson and song sections.

## F. Songs and the stage

70. **Read song facts from Guitar Pro files** (M). Tuning, tempo, key and sections pulled from the file on
    import, to pre-fill the song's sections (see D55).
71. **Videos by role** (S). For each song, search links split into lesson / backing track / guitar only,
    plus any link you pin.
72. **Stage mode** (M). A full-screen chart, adjustable size, auto-scroll at ten speeds, a click at the
    song's tempo, and "up next". Arrows, PageUp/PageDown or a foot pedal turn pages.
73. **Setlists** (M). Order songs for a session or a gig, with a warning when two songs in a row need
    different tunings. The tuner preset follows the song.
74. **Song readiness ring** (S). One number per song (the average of its sections), the same ring style
    as the exercise result.

## G. Tone rig

75. **More generic pedals** (L). Ring modulator, envelope filter, rotary speaker, harmonic tremolo, optical
    compressor, octave-up fuzz, transparent overdrive and mid-hump asymmetric overdrive. Each one is
    designed from its behavior, with generic names only.
76. **"How it works" per pedal** (M). A short explanation in our own words (clipping, tone stack, LFO,
    delay line), with a small frequency-response or waveform drawing.
77. **Clipping visualizer** (S). A test sine before and after the drive: soft, hard and asymmetric
    clipping side by side. Measured at the pre-master tap, never played out loud.
78. **Amp tone-stack curve** (S). Draw the EQ curve the bass/mid/treble knobs make, updated while you turn
    them.
79. **Tone recipes per song section** (M). Saved rig presets tied to a song section ("clean verse", "lead
    solo"), shown with the chain and knob values.
80. **Capture your own amp (research)** (L). Record a DI and the amp's output, fit a small model offline,
    and load it as an amp type. A research spike, written from scratch.

## H. Interface and usability

81. **Status chips in every header** (S). Tuning · key · BPM · time signature as small chips on song,
    chart and exercise screens. Each chip has a label, not only a color.
82. **Section status as a chip row** (M). Each song section shows its five states as clickable chips, so
    one click updates the state. A "+" sends the section to today's queue.
83. **Today's queue as cards** (M). Each item shows why it's there (added by you / review / next lesson),
    its state, its minutes and a "practice" button. Pinned items stay until you clear them.
84. **Stats header** (S). Songs · sessions · hours · days in a row as big numbers at the top of the
    progress view.
85. **Bottom dock on desktop** (M, explore). A floating icon dock for the main sections as an alternative
    to the side rail, to test which one people prefer.
86. **Keyboard everywhere** (M). Every practice screen gets shortcuts (space, arrows, M for metronome,
    +/− for size, Esc), shown in a one-line footer that hides on touch screens.
87. **Explicit practice states** (M). Preparing → ready → playing → paused → feedback → finished →
    audio unavailable, each with its own message and actions. "Audio unavailable" keeps the visual
    tasks working.
88. **First action before the explanation** (S). In every lesson the first thing you can do (play, choose a
    note) comes before the text. The theory is one tap away.
89. **Phone-first practice controls** (M). Start, stop, repeat and hint fit in the bottom of a portrait
    phone screen, reachable with the guitar on your lap.
90. **Restore without auto-playing** (S). Settings and progress come back on reload, but nothing ever
    starts making sound by itself.
91. **"Next, and why"** (S). When an exercise or lesson ends, say what to do next and why ("you passed the
    shapes; now the same change at 90 BPM").
92. **Graceful missing features** (S). When an optional part is missing (no input device, no MIDI, no
    file), its screen says so and how to fix it, instead of breaking or hiding.
93. **Settings that show where a value comes from** (S). Shows whether a value is the default, saved by
    you, or set by the environment, so a hidden override is never a mystery.
94. **Screenshots generated by a script** (S). A Playwright script that boots the app with demo data and
    regenerates the README screenshots, in both themes.
95. **Design tokens file** (S). Move colors, radii, shadows and spacing into one tokens block, document
    them, and use them in the rig's hardware finishes too.
96. **Inline row expansion** (M). Lists (songs, charts, lessons) open details in place instead of
    navigating away, keeping your scroll position.

---

### Suggested order

1. Method first, since it shapes everything else: D49–D52, D59, H87, H88.
2. The theory backbone: A3–A10, B18–B23, with the spelling engine A8 early.
3. Jazz: C34–C46 on top of B28–B33 and the voice-leading engine B32.
4. Practice and songs: D54–D56, E62–E63, F70, F72, H81–H84.
5. Tone and polish: G75–G78, H85–H96.
