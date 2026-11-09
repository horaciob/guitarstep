"""End-to-end flows through the web UI."""
import re

import pytest

from playwright.sync_api import expect


def go(page, route=""):
    page.goto(f"{page.base}/#/{route}")


def onboarded(page):
    page.goto(page.base + "/static/index.html")      # same origin, to set storage before the app runs
    page.evaluate("localStorage.setItem('guitarr.onboarded', '1')")


def test_first_run_opens_the_setup_and_can_be_skipped(app_page):
    go(app_page)
    expect(app_page).to_have_url(re.compile("#/setup"))
    expect(app_page.get_by_role("heading", name="Let's get guitarr listening to you")).to_be_visible()
    app_page.get_by_role("button", name="Skip, I'll explore").click()
    expect(app_page).to_have_url(re.compile("#/home"))
    expect(app_page.locator(".plan-card")).to_be_visible()


def test_practice_empty_state_loads_the_demo(app_page):
    onboarded(app_page)
    go(app_page, "practice")
    expect(app_page.locator("#pEmpty")).to_be_visible()
    app_page.locator("#demoBtn").click()
    expect(app_page.locator("#pEmpty")).to_be_hidden()
    expect(app_page.locator("#pSong")).to_have_value("demo-reference.mid")
    expect(app_page.locator("#nowWhere")).to_contain_text("bars")


def test_plan_validation_categories_and_timer(app_page):
    onboarded(app_page)
    go(app_page, "plan")
    expect(app_page.get_by_role("heading", name="Practice plan")).to_be_visible()
    app_page.locator("#planEdit summary").click()
    app_page.locator("#m_techniqueM").fill("-5")
    app_page.get_by_role("button", name="Save changes").click()
    expect(app_page.locator("#err_technique")).to_have_text("Time can't be negative.")
    app_page.locator("#m_techniqueM").fill("10")
    expect(app_page.locator("#err_technique")).to_be_hidden()

    app_page.locator("#newName").fill("Scales")
    app_page.locator("#newM").fill("5")
    app_page.get_by_role("button", name="Add", exact=True).click()
    row = app_page.locator(".cat-row", has_text="Scales")
    expect(row).to_be_visible()
    app_page.locator("#newName").fill("  scáles ")
    app_page.get_by_role("button", name="Add", exact=True).click()
    expect(app_page.locator("#newErr")).to_have_text("There's already a category with that name.")

    row.get_by_role("button", name="Remove").click()
    row.get_by_role("button", name="Yes").click()
    expect(app_page.locator(".cat-row", has_text="Scales")).to_have_count(0)

    app_page.locator(".cat", has_text="Theory").get_by_role("button", name="Start the timer").click()
    expect(app_page.locator("#timerPill")).to_be_visible()
    expect(app_page.locator("#timerPillName")).to_contain_text("Theory")
    app_page.locator("#timerPillPause").click()
    expect(app_page.locator("#timerPillName")).to_contain_text("paused")


def test_rig_hardware_look_quick_sounds_and_mic(app_page):
    onboarded(app_page)
    go(app_page, "rig")                            # the rig stays off: nothing is played
    app_page.locator('#rigQuick .quick[data-id="sixties_fuzz"]').click()
    expect(app_page.locator('#rigQuick .quick[data-id="sixties_fuzz"]')).to_contain_text("active")
    expect(app_page.locator("#sec-amp .amp")).to_have_class(re.compile("skin-chime"))
    fuzz = app_page.locator("#sec-pedals .pedal.stomp", has_text="Fuzz")
    expect(fuzz.locator(".stomp-led small")).to_have_text("ON")
    fuzz.locator(".footswitch").click()
    expect(fuzz.locator(".stomp-led small")).to_have_text("OFF")
    expect(fuzz).not_to_have_class(re.compile(r"\bon\b"))
    app_page.locator('#ampTypes .pick[data-id="high_gain"]').click()
    expect(app_page.locator("#sec-amp .amp")).to_have_class(re.compile("skin-high_gain"))
    app_page.locator('#cabTypes .pick[data-id="c4x12_closed"]').click()
    expect(app_page.locator("#sec-cab .speaker")).to_have_count(4)
    mic = app_page.locator("#sec-cab .cab-mic")
    before = mic.evaluate("m => m.style.getPropertyValue('--x')")
    app_page.locator('#micKnobs .knob[aria-label="Position"]').focus()
    app_page.keyboard.press("End")
    expect(mic).to_have_attribute("style", re.compile(r"--x: 42"))
    assert before != "42.0%"


def test_rig_effects_and_presets(app_page):
    onboarded(app_page)
    go(app_page, "rig")
    expect(app_page.get_by_role("heading", name="Amp & effects")).to_be_visible()
    before = app_page.locator("#sec-pedals .pedal[data-uid]").count()
    app_page.locator("[data-add=pedals]").click()
    app_page.locator("#fxDialog .pick[data-id=fuzz]").click()
    expect(app_page.locator("#sec-pedals .pedal[data-uid]")).to_have_count(before + 1)

    app_page.get_by_role("button", name="Save", exact=True).click()
    app_page.locator("#presetName").fill("My test tone")
    app_page.locator("#saveForm button[type=submit]").click()
    expect(app_page.locator("#rigPreset")).to_contain_text("My test tone")
    app_page.locator("#rigDel").click()
    app_page.locator("#rigDelYes").click()
    expect(app_page.locator("#rigPreset")).not_to_contain_text("My test tone")


def test_settings_and_language(app_page):
    onboarded(app_page)
    go(app_page, "settings")
    expect(app_page.get_by_role("heading", name="Audio settings")).to_be_visible()
    app_page.locator("#langSelect").select_option("es")
    expect(app_page.locator("#nav")).to_contain_text("Plan de práctica")
    app_page.evaluate("localStorage.removeItem('guitarr.lang')")


def test_every_page_renders_without_errors(app_page):
    onboarded(app_page)
    for route in ["home", "plan", "course", "lesson/" , "chords", "practice", "charts", "rig", "tuner",
                  "tools", "tools?tab=drill", "tools?tab=fretboard", "analyze", "history", "settings", "camera"]:
        go(app_page, route)
        app_page.wait_for_timeout(250)
    expect(app_page.locator("#main")).to_be_visible()


def test_backup_download_and_restore(app_page, tmp_path):
    onboarded(app_page)
    go(app_page, "settings")
    with app_page.expect_download() as dl:
        app_page.locator("#bkDownload").click()
    path = tmp_path / dl.value.suggested_filename
    dl.value.save_as(path)
    assert path.name.startswith("guitarr-backup-") and path.stat().st_size > 0
    app_page.locator("#bkFile").set_input_files(str(path))
    app_page.locator("#bkYes").click()
    expect(app_page.locator("#bkStatus")).to_contain_text("Restored")


def test_rig_impulse_response_is_kept_on_the_server(app_page, tmp_path):
    import numpy as np
    import soundfile as sf

    ir = tmp_path / "Room 4x12.wav"
    sf.write(ir, np.r_[1.0, np.zeros(2399)].astype("float32"), 48000)
    onboarded(app_page)
    go(app_page, "rig")
    app_page.locator("#irFile").set_input_files(str(ir))
    expect(app_page.locator(".ir-list li.on")).to_contain_text("Room 4x12.wav")
    app_page.reload()                                       # still there after a reload
    expect(app_page.locator(".ir-list li.on")).to_contain_text("Room 4x12.wav")
    app_page.locator("[data-ir-del]").click()
    expect(app_page.locator(".ir-list li")).to_have_count(0)


def test_today_practice_on_home_and_deep_links(app_page):
    onboarded(app_page)
    go(app_page, "home")
    steps = app_page.locator(".today-steps li")
    expect(steps.first).to_contain_text("Tune up")
    app_page.locator("[data-tick=tune]").click()
    expect(steps.first).to_have_class(re.compile("done"))
    drill = app_page.locator(".today-steps li", has_text="Chord-change minute")
    drill.get_by_role("link").click()
    expect(app_page).to_have_url(re.compile("tab=drill"))
    go(app_page, "chords?chord=G")
    expect(app_page.locator('.chord-card.focus[data-id="G"]')).to_be_visible()


def test_reminder_settings_are_saved(app_page):
    onboarded(app_page)
    go(app_page, "settings")
    app_page.locator("#remTime").fill("07:45")
    app_page.locator("#remOn").check()
    expect(app_page.locator("#remStatus")).to_contain_text("Reminder saved")
    import json
    import urllib.request
    r = json.load(urllib.request.urlopen(app_page.base + "/api/reminder"))
    assert r["enabled"] and r["time"] == "07:45" and "{left}" in r["body"]


def test_rig_tuner_and_midi_expression(app_page):
    onboarded(app_page)
    go(app_page, "rig")
    expect(app_page.get_by_role("heading", name="Amp & effects")).to_be_visible()
    result = app_page.evaluate("""async () => {
      const { rig } = await import('/static/lib/rig/engine.js');
      const { makeEffect } = await import('/static/lib/rig/presets.js');
      await rig.setSource({ kind: 'virtual', riff: 'sustained' });
      await rig.start();
      rig.setTuning(true);
      const notes = new Set();
      for (let i = 0; i < 60; i++) { const p = rig.pitch(); if (p) notes.add(p.note); await new Promise(r => setTimeout(r, 100)); }
      rig.setTuning(false);
      const vol = makeEffect('volume');
      rig.addEffect('pedals', vol);
      rig.learnMidi(true);
      rig.onMidi([0xB0, 11, 0]);                       // learns CC 11
      rig.setMidiTarget(vol.uid + ':level');
      rig.onMidi([0xB0, 11, 127]);
      const top = rig.find(vol.uid).e.params.level;
      rig.onMidi([0xB0, 11, 64]);
      const mid = rig.find(vol.uid).e.params.level;
      rig.onMidi([0x90, 11, 10]);                      // a note-on is ignored
      await rig.stop();
      return { notes: [...notes], cc: rig.source.midi.cc, top, mid };
    }""")
    assert "E4" in result["notes"], result
    assert result["cc"] == 11 and result["top"] == 10 and abs(result["mid"] - 5.04) < 0.01


def test_rig_records_a_wav_with_the_effects(app_page):
    onboarded(app_page)
    go(app_page, "rig")
    expect(app_page.get_by_role("heading", name="Amp & effects")).to_be_visible()
    info = app_page.evaluate("""async () => {
      const { rig } = await import('/static/lib/rig/engine.js');
      await rig.setSource({ kind: 'virtual', riff: 'power_riff' });
      await rig.start();
      rig.startRecording();
      await new Promise(r => setTimeout(r, 1500));
      const blob = rig.stopRecording();
      await rig.stop();
      const head = new Uint8Array(await blob.slice(0, 12).arrayBuffer());
      const pcm = new Int16Array(await blob.slice(44).arrayBuffer());
      let peak = 0; for (const v of pcm) peak = Math.max(peak, Math.abs(v));
      return { riff: String.fromCharCode(...head.slice(0, 4)), wave: String.fromCharCode(...head.slice(8, 12)),
               seconds: rig.lastTakeSeconds, peak };
    }""")
    assert info["riff"] == "RIFF" and info["wave"] == "WAVE"
    assert 1.0 < info["seconds"] < 2.5 and info["peak"] > 100       # it's not silence
    expect(app_page.locator("#recDl")).to_be_visible()


def test_chart_practice_offers_a_backing_track(app_page):
    onboarded(app_page)
    go(app_page, "practice?chart=01-em-am")
    expect(app_page.locator("#pChartBanner")).to_be_visible()
    expect(app_page.locator("#pBackingWrap")).to_be_visible()
    app_page.locator("#pChartClear").click()
    expect(app_page.locator("#pBackingWrap")).to_be_hidden()


def test_chart_exercise_shows_a_guide_and_plays_a_demo(app_page):
    onboarded(app_page)
    go(app_page, "lesson/first-change")
    box = app_page.locator('.exercise[data-id="em-am-chart"]')
    guide = box.locator(".ex-guide")
    expect(guide).to_contain_text("One strum per beat")
    expect(guide).to_contain_text("♩ = 49 (70%")
    expect(guide.locator(".bar-cell span")).to_have_count(8)
    demo = box.locator("[data-act=hear]")
    demo.click()                                   # headless Chromium has no audio output
    expect(demo).to_have_text("■")
    expect(guide.locator(".g-pos")).to_contain_text("Count-in")
    expect(guide.locator(".bar-cell span.on")).to_have_count(1, timeout=10_000)
    expect(guide.locator(".strum span.on")).to_have_count(1)
    expect(guide.locator(".g-pos")).to_contain_text("bar 1 of 8")
    expect(guide.locator(".g-next")).to_contain_text("next: Am in")
    demo.click()
    expect(demo).to_have_text("♪")
    expect(guide.locator(".bar-cell span.on")).to_have_count(0)


def _fake_listener(page, report=None):
    """Answers /api/live/* in the browser, so no microphone or metronome output is ever opened.
    `report` is what the take ends with once stopped (by default: nothing played)."""
    import json
    import time

    live = {}
    report = report or {"award": {"passed": False, "need": 80}, "summary": {"score": None}}

    def handle(route):
        url = route.request.url
        if url.endswith("/start"):
            live.update(t0=time.monotonic(), stopped=False)
            body = {"ok": True}
        elif url.endswith("/stop"):
            live["stopped"] = True
            body = {"ok": True}
        elif "t0" not in live:                                      # polled before anything started
            body = {"active": False, "state": None, "report": None}
        elif live.get("stopped"):
            body = {"active": False, "state": None, "report": report}
        else:
            beat = (time.monotonic() - live["t0"]) * 49 / 60 - 4       # 4-beat count-in at 49 BPM
            body = {"active": True, "report": None, "state": {"k": 0, "total": 8, "pos": beat, "lane": [], "last": None,
                                                              "countdown": None if beat >= 0 else -int(beat // 1)}}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("**/api/live/**", handle)


def test_exercise_opens_on_its_own_screen_with_a_big_metronome(app_page):
    onboarded(app_page)
    _fake_listener(app_page)
    go(app_page, "lesson/first-change")
    app_page.locator('.exercise[data-id="em-am-chart"] [data-act=go]').click()
    focus = app_page.locator("dialog.ex-focus")
    expect(focus).to_be_visible()
    expect(focus.locator("#fTitle")).to_have_text("With the metronome at 70%")
    expect(focus.locator(".f-metro .metro-dots i")).to_have_count(4)
    expect(focus.locator(".f-num b").first).to_have_text("49")
    expect(focus.locator(".focus-guide .bar-cell span")).to_have_count(8)
    expect(focus.locator(".f-metro .metro-dots i.on")).to_have_count(1, timeout=10_000)   # follows the listener
    focus.locator("[data-f=go]").click()           # stop
    expect(focus.locator("[data-f=go]")).to_have_text(re.compile("Again"), timeout=10_000)
    expect(focus.locator(".f-metro .metro-dots i.on")).to_have_count(0)
    demo = focus.locator("[data-f=hear]")
    demo.click()                                   # headless Chromium has no audio output
    expect(focus.locator(".f-metro .metro-dots i.on")).to_have_count(1, timeout=10_000)
    expect(focus.locator(".focus-guide .bar-cell span.on")).to_have_count(1, timeout=10_000)
    expect(focus.locator(".f-beat")).to_have_text(re.compile("^[1-4]$"))
    app_page.keyboard.press("Escape")
    expect(focus).to_be_hidden()
    expect(app_page.locator(".exercise").first).to_be_visible()


def test_lesson_continue_keys_and_result_ring(app_page):
    onboarded(app_page)
    _fake_listener(app_page, {"award": {"passed": True, "need": 75, "xp": 20}, "summary": {"score": 91}})
    go(app_page, "lesson/first-change")
    cont = app_page.locator("#exContinue")
    expect(cont).to_contain_text("Continue: Strum Am four times")
    cont.click()
    focus = app_page.locator("dialog.ex-focus")
    expect(focus.locator("#fTitle")).to_have_text("Strum Am four times")
    expect(focus.locator("[data-f=go]")).to_contain_text("Listen to me")      # opened, not started
    app_page.keyboard.press(" ")                                              # start
    expect(focus.locator("[data-f=go]")).to_contain_text("Stop")
    app_page.keyboard.press(" ")                                              # stop → the take is graded
    ring = focus.locator(".f-result")
    expect(ring).to_be_visible()
    expect(ring).to_contain_text("91%")
    expect(ring).to_contain_text("passed!")
    expect(ring).to_contain_text("+20 XP")
    app_page.keyboard.press("Enter")                                          # next exercise
    expect(focus.locator("#fTitle")).to_contain_text("Em → Am")
    expect(ring).to_be_hidden()


def test_course_shows_progress_per_level(app_page):
    onboarded(app_page)
    go(app_page, "course")
    expect(app_page.locator(".level").first.locator(".lvl-prog")).to_contain_text("0 of 5 lessons")


def test_quiz_exercise_is_answered_and_graded_on_the_server(app_page):
    onboarded(app_page)
    go(app_page, "lesson/intervals")
    box = app_page.locator('.exercise[data-id="interval-frets-quiz"]')
    expect(box).to_contain_text("you pass it by answering")
    box.locator("[data-act=go]").click()
    focus = app_page.locator("dialog.ex-focus")
    for i in range(6):
        expect(focus.locator(".q-count")).to_have_text(f"Question {i + 1} of 6")
        expect(focus.locator(".q-prompt")).to_contain_text("which interval is it?")
        app_page.keyboard.press("1")                                         # answer with the number keys
        expect(focus.locator(".q-feedback")).not_to_be_empty()
        expect(focus.locator(".q-choice.right")).to_have_count(1)             # the right one is always shown
        focus.locator("[data-q=next]").click()
    expect(focus.locator(".f-result")).to_be_visible()
    expect(focus.locator(".f-result .r-text b")).to_have_text(re.compile(r"^\d+%$"))


def test_pick_notes_on_the_fretboard(app_page):
    onboarded(app_page)
    go(app_page, "lesson/build-triads")
    expect(app_page.locator(".lesson-figure svg.fb .fb-dot.root").first).to_be_visible()   # the lesson's figure
    app_page.locator('.exercise[data-id="triad-pick"] [data-act=go]').click()
    focus = app_page.locator("dialog.ex-focus")
    expect(focus.locator(".q-prompt")).to_contain_text("Build ")
    focus.locator('.fb-pos[data-s="2"][data-f="1"]').click()                  # C on the B string
    expect(focus.locator(".fb-dot.sel")).to_have_count(1)
    focus.locator("[data-q=check]").click()
    expect(focus.locator(".q-feedback")).to_contain_text("Not quite")       # one note can't be a triad
    expect(focus.locator("[data-q=next]")).to_be_visible()


def test_drawn_targets_and_theory_figures(app_page):
    onboarded(app_page)
    _fake_listener(app_page, {"award": {"passed": False, "need": 80}, "summary": {"score": 40}})
    go(app_page, "lesson/sharps-flats")
    expect(app_page.locator(".lesson-figure svg.piano")).to_be_visible()
    expect(app_page.locator(".lesson-figure svg.piano")).to_contain_text("C♯")
    app_page.locator('.exercise[data-id="naturals-play"] [data-act=go]').click()
    focus = app_page.locator("dialog.ex-focus")
    expect(focus.locator(".drawn-list li")).to_have_count(5)
    expect(focus.locator(".f-prompt")).to_contain_text("on string")
    focus.locator("[data-f=go]").click()                                     # stop → the answers are revealed
    expect(focus.locator(".drawn-list li").first).to_contain_text("fret")
    app_page.keyboard.press("Escape")
    go(app_page, "lesson/major-scale")
    expect(app_page.locator('.exercise[data-id="c-one-string"] pre.tab')).to_contain_text("A|-3")
    go(app_page, "lesson/drop2")
    expect(app_page.locator('.exercise[data-id="drop2-top"] .ex-shapes .mini-chord')).to_have_count(3)


def test_tuning_and_left_handed(app_page):
    onboarded(app_page)
    go(app_page, "settings")
    expect(app_page.locator("#iTuning option")).to_have_count(10)
    app_page.locator("#iTuning").select_option("drop_d")
    expect(app_page.locator("#iStatus")).to_contain_text("Instrument saved")
    go(app_page, "tuner")
    expect(app_page.locator("#tStrings")).to_contain_text("D2")
    go(app_page, "settings")
    app_page.locator("#iTuning").select_option("seven_string")
    app_page.locator("#iLefty").check()
    expect(app_page.locator("#iStatus")).to_contain_text("Instrument saved")
    app_page.reload()
    go(app_page, "tools?tab=fretboard")
    expect(app_page.locator("#fbNeck svg.fb")).to_have_attribute("viewBox", "0 0 1000 256")   # 7 strings
    go(app_page, "chords")
    expect(app_page.locator(".callout", has_text="standard tuning")).to_be_visible()
    label = app_page.locator(".chord-card").first.locator("svg text").last
    expect(label).to_have_text("E  B  G  D  A  E")                                      # mirrored


def test_fretboard_explorer_and_chord_finder(app_page):
    onboarded(app_page)
    go(app_page, "tools?tab=fretboard")
    app_page.locator("#root").select_option("Gb")
    app_page.locator("#scale").select_option("major")
    expect(app_page.locator("#fbNotes")).to_contain_text("Cb (4)")              # spelled from the key
    app_page.locator("#labels").select_option("degree")
    expect(app_page.locator("#fbNeck .fb-txt.root").first).to_have_text("1")
    app_page.locator("#window").select_option("2")                            # frets 2–5
    expect(app_page.locator("#fbNeck .fb-pos")).to_have_count(24)

    go(app_page, "tools?tab=finder")
    expect(app_page.locator("#cfTones")).to_contain_text("Cmaj7: C (1) · E (3) · G (5) · B (7)")
    expect(app_page.locator("#cfGrid .cf-card").first).to_be_visible()
    app_page.locator("#cfQ").select_option("maj")
    expect(app_page.locator("#cfGrid")).to_contain_text("need a chord with a 7th")   # drop 2 of a triad

    app_page.locator("#cfMode button", has_text="Name a chord").click()
    for s, f in ((5, 3), (4, 2), (3, 0)):                                      # C E G
        app_page.locator(f'#cfNeck .fb-pos[data-s="{s}"][data-f="{f}"]').click()
    expect(app_page.locator("#cfNames")).to_contain_text("C")
    app_page.locator('#cfNeck .fb-pos[data-s="5"][data-f="2"]').click()          # B on the same string replaces the C
    expect(app_page.locator("#cfNeck .fb-dot.sel")).to_have_count(3)
    expect(app_page.locator("#cfNames")).to_contain_text("Em/B")

    app_page.locator("#cfMode button", has_text="Voice-lead").click()
    expect(app_page.locator("#cfLGrid .cf-card")).to_have_count(4)
    app_page.locator("#cfProg").fill("Dm7")
    app_page.locator("#cfForm button[type=submit]").click()
    expect(app_page.locator("#cfErr")).to_contain_text("2 to 16 chords")
    expect(app_page.locator("#cfProg")).to_have_value("Dm7")                    # what you typed stays


def test_phone_layout_and_install_manifest(page, server_url):
    import json
    import urllib.request
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(server_url + "/static/index.html")
    page.evaluate("localStorage.setItem('guitarr.onboarded', '1')")
    page.goto(server_url + "/#/home")
    expect(page.locator("#tabbar")).to_be_visible()
    expect(page.locator("#nav")).to_be_hidden()
    page.locator("#navToggle").click()
    expect(page.locator("#nav")).to_be_visible()
    page.locator("#nav a[data-route=plan]").click()
    expect(page).to_have_url(re.compile("#/plan"))
    expect(page.locator("#nav")).to_be_hidden()
    expect(page.locator("#tabbar a[data-route=plan]")).to_have_class(re.compile("active"))
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    m = json.load(urllib.request.urlopen(server_url + "/static/manifest.json"))
    assert m["display"] == "standalone" and {"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]}
    for icon in m["icons"]:
        assert urllib.request.urlopen(server_url + icon["src"]).status == 200


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_accessibility_audit(browser, server_url, scheme):
    """axe-core finds no violations on the main pages, in both themes."""
    axe_mod = pytest.importorskip("axe_playwright_python.sync_playwright")
    page = browser.new_page(color_scheme=scheme, viewport={"width": 1280, "height": 900})
    page.goto(server_url + "/static/index.html")
    page.evaluate("localStorage.setItem('guitarr.onboarded', '1')")
    axe = axe_mod.Axe()
    problems = []
    for route in ["home", "plan", "course", "lesson/strings", "lesson/first-change", "chords", "practice", "charts", "rig", "tuner",
                  "tools", "tools?tab=drill", "tools?tab=fretboard", "analyze", "history", "settings", "setup"]:
        page.goto(f"{server_url}/#/{route}")
        page.wait_for_timeout(500)
        for v in axe.run(page).response["violations"]:
            problems.append(f"{route}: {v['id']} ({len(v['nodes'])}) {v['nodes'][0]['target']}")
    page.close()
    assert not problems, "\n".join(problems)


def test_signal_check_walkthrough(app_page):
    """The whole guided check, fed by the demo take instead of a guitar."""
    import json
    import urllib.request
    onboarded(app_page)
    take = json.load(urllib.request.urlopen(urllib.request.Request(app_page.base + "/api/demo", method="POST")))["take"]
    go(app_page, f"signal?simulate={take}")
    expect(app_page.locator("#sgSource")).to_contain_text("demo-take")
    app_page.locator("#sgRec").click()                                   # silence (the take plays: not silent)
    expect(app_page.locator(".sg-result")).to_be_visible(timeout=15000)
    app_page.get_by_role("button", name="Continue").click()
    expect(app_page.locator(".checklist li")).to_have_count(6)
    app_page.get_by_role("button", name="Continue").click()
    expect(app_page.locator("#sgCoach")).to_be_visible()
    app_page.locator("#sgRec").click()                                   # strum level
    expect(app_page.locator(".sg-result")).to_be_visible(timeout=15000)
    app_page.locator("[data-go=notes]").click()
    app_page.locator("#sgRec").click()                                   # notes (14 s)
    expect(app_page.locator(".sg-result")).to_contain_text("Best settings", timeout=30000)
    app_page.locator("[data-go=listen]").click()
    expect(app_page.locator("[data-play=notes]")).to_be_visible()
    app_page.locator("[data-go=done]").click()
    app_page.locator("#sgSave").click()
    expect(app_page).to_have_url(re.compile("#/practice"))
    cfg = json.load(urllib.request.urlopen(app_page.base + "/api/config"))["audio"]
    assert cfg["gate_db"] is not None and cfg["sensitivity"] is not None


def test_lesson_steps_glossary_guidance_and_review_link(app_page):
    onboarded(app_page)
    go(app_page, "lesson/major-scale")
    steps = app_page.locator(".stepper li")
    expect(steps).to_have_count(5)
    expect(steps.first).to_contain_text("Discover")
    expect(app_page.locator(".meters-row")).to_contain_text("Understood 0 of 1")
    expect(app_page.locator(".meters-row")).to_contain_text("Played 0 of 2")
    term = app_page.locator(".theory button.term").first
    term.click()
    expect(app_page.locator("#termDialog")).to_be_visible()
    app_page.keyboard.press("Escape")
    # a review on the home page opens the exercise straight away, with the guidance choice
    go(app_page, "lesson/major-scale?ex=g-position")
    focus = app_page.locator("dialog.ex-focus")
    expect(focus.locator("#fTitle")).to_have_text("G major in one position")
    expect(focus.locator("#fGuide button")).to_have_count(3)
    expect(focus.locator(".focus-body pre.tab")).to_be_visible()
    focus.locator('#fGuide button[data-g="2"]').click()                      # no help: no tab, no names
    expect(focus.locator(".focus-body pre.tab")).to_have_count(0)
    expect(focus.locator(".f-now")).to_have_text("?")


def test_level_recap_and_test_out_entry(app_page):
    onboarded(app_page)
    go(app_page, "course")
    from guitarr import catalog
    number = next(lv["number"] for lv in catalog.course()["levels"] if lv["id"] == "n8")   # levels get inserted
    expect(app_page.locator(".lesson", has_text=f"Level {number} recap")).to_be_visible()
    go(app_page, "lesson/recap-n8")
    expect(app_page.locator(".exercise").first).to_contain_text("Half steps, whole steps and two names")
    expect(app_page.locator("#testOut")).to_have_count(0)                   # a recap can't be skipped
    go(app_page, "lesson/intervals")
    app_page.locator("#testOut").click()
    focus = app_page.locator("dialog.ex-focus")
    expect(focus.locator("#fTitle")).to_have_text("Test out of this lesson")
    focus.locator("[data-f=go]").click()
    expect(focus.locator(".q-count")).to_have_text("Question 1 of 2")


def test_chart_sections_progress(app_page):
    onboarded(app_page)
    go(app_page, "chart/25-song-form-aaba")
    rows = app_page.locator(".sec-row")
    expect(rows).to_have_count(4)
    expect(rows.nth(2)).to_contain_text("bars 17–24")
    rows.nth(2).locator('[data-st="ready"]').click()
    expect(app_page.locator(".mastery")).to_contain_text("25%")
    expect(app_page.locator(".sec-row").nth(2).locator('[data-st="ready"]')).to_have_attribute("aria-pressed", "true")
    expect(app_page.locator(".sec-row").nth(2).locator("a")).to_have_attribute("href", re.compile("from=17&to=24"))


def test_practice_tools_render_and_respond(app_page):
    onboarded(app_page)
    go(app_page, "tools?tab=metronome")
    dot = app_page.locator("#dots .dot").nth(1)
    dot.click()                                                            # normal → silent
    expect(dot).to_have_attribute("aria-label", re.compile("silent"))
    expect(app_page.locator("#subs option")).to_have_count(6)
    go(app_page, "tools?tab=random")
    key = app_page.locator(".rand-field").first
    key.locator("[data-lock]").click()
    expect(app_page.locator(".rand-field").first).to_have_class(re.compile("locked"))
    locked = app_page.locator(".rand-field").first.locator("b").inner_text()
    for _ in range(3):
        app_page.locator("#roll").click()
    expect(app_page.locator(".rand-field").first.locator("b")).to_have_text(locked)   # the locked field stays
    expect(app_page.locator("#randNeck svg.fb")).to_be_visible()
    go(app_page, "tools?tab=rhythm")
    expect(app_page.locator("#rGo")).to_be_visible()
    go(app_page, "tools?tab=strums")
    expect(app_page.locator(".strum-card")).to_have_count(11)
    expect(app_page.locator(".strum-card", has_text="Waltz").first).to_contain_text("3/4")
    go(app_page, "tools?tab=ear&ear=chord_quality")
    app_page.locator("#earGo").click()
    expect(app_page.locator(".q-choice")).to_have_count(6)
    app_page.keyboard.press("1")
    expect(app_page.locator(".q-reveal svg.chord-svg")).to_be_visible()     # the shape of what you heard
    go(app_page, "tools?tab=fretboard")
    app_page.locator("#root").select_option("D")
    app_page.locator("#scale").select_option("dorian")
    app_page.locator("#over").select_option("m7")
    app_page.locator("#labels").select_option("degree")
    expect(app_page.locator("#fbNotes")).to_contain_text("E (9)")
    expect(app_page.locator("#fbNotes")).to_contain_text("B (13)")
    expect(app_page.locator("#fbNeck .fb-dot.mark").first).to_be_visible()


def test_stats_and_time_budget(app_page):
    onboarded(app_page)
    go(app_page, "plan")
    expect(app_page.locator("svg.heatmap rect")).to_have_count(365)
    expect(app_page.locator(".hm-legend")).to_contain_text("60+ min")
    go(app_page, "home")
    app_page.locator('[data-budget="30"]').click()
    expect(app_page.locator('[data-budget="30"]')).to_have_attribute("aria-pressed", "true")
    expect(app_page.locator(".today-plan")).to_contain_text("0:30")
    go(app_page, "chart/new?strum=D.D.D.&time=3/4")
    expect(app_page.locator("#txt")).to_have_value(re.compile(r"strum: D\.D\.D\.\n"))
    expect(app_page.locator("#txt")).to_have_value(re.compile(r"time: 3/4"))


def test_setlist_and_stage(app_page):
    onboarded(app_page)
    go(app_page, "setlists")
    app_page.locator("#newForm button[type=submit]").click()
    expect(app_page.locator("#newErr")).to_contain_text("name")              # the error goes under the field
    app_page.locator("#newName").fill("Gig")
    app_page.locator("#newForm button[type=submit]").click()
    expect(app_page.locator("#openTitle")).to_have_text("Gig")
    app_page.locator("#addChart").select_option("01-em-am")
    expect(app_page.locator(".setlist-item")).to_have_count(1)
    app_page.locator("#addChart").select_option("02-d-a-e")
    expect(app_page.locator(".setlist-item")).to_have_count(2)
    app_page.locator(".setlist-item").nth(1).locator("[data-act=up]").click()
    expect(app_page.locator(".setlist-item").first).to_contain_text("D, A and E")
    app_page.locator(".setlist-item").nth(1).locator("[data-act=remove]").click()
    app_page.locator(".setlist-item").nth(1).locator("[data-no]").click()       # confirm in place: No keeps it
    expect(app_page.locator(".setlist-item")).to_have_count(2)
    app_page.get_by_role("link", name="Start on stage").click()
    expect(app_page.locator(".stage-title")).to_contain_text("D, A and E")
    expect(app_page.locator(".rail")).to_be_hidden()
    expect(app_page.locator(".stage-next")).to_contain_text("First change")
    app_page.keyboard.press("PageDown")                                       # a foot pedal sends PageDown
    expect(app_page.locator(".stage-title")).to_contain_text("First change")
    app_page.keyboard.press("+")
    expect(app_page.locator(".stage-mode")).to_have_attribute("style", re.compile("1.2"))
    app_page.keyboard.press("Escape")
    expect(app_page).to_have_url(re.compile("#/setlists"))


def test_song_page_from_a_guitar_pro_file(app_page):
    import guitarpro
    from guitarpro import models as m

    from guitarr import config
    song = m.Song(tempo=100)
    song.title = "My tune"
    for _ in range(3):
        song.newMeasure()
    song.measureHeaders[0].marker = m.Marker(title="Intro")
    song.measureHeaders[2].marker = m.Marker(title="Chorus")
    voice = song.tracks[0].measures[0].voices[0]                              # a few notes, so Practice can preview it
    for k, (s, f) in enumerate([(6, 0), (5, 2), (4, 2)]):
        b = m.Beat(voice, start=song.tracks[0].measures[0].start + k * 960, status=m.BeatStatus.normal, duration=m.Duration(value=4))
        b.notes.append(m.Note(b, value=f, string=s, type=m.NoteType.normal))
        voice.beats.append(b)
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    guitarpro.write(song, str(config.SONGS_DIR / "mine.gp5"))
    onboarded(app_page)
    go(app_page, "song/mine.gp5")
    expect(app_page.locator("#view h1")).to_have_text("My tune")
    expect(app_page.locator(".status-chips")).to_contain_text("BPM 100")
    expect(app_page.locator(".sec-row")).to_have_count(2)
    app_page.locator(".sec-row").first.locator('[data-st="solid"]').click()
    expect(app_page.locator(".ready-ring")).to_contain_text("38%")
    expect(app_page.locator(".tutorias li")).to_have_count(3)
    app_page.locator("#vidUrl").fill("not a link")
    app_page.locator("#vidForm button").click()
    expect(app_page.locator("#vidErr")).to_contain_text("http")
    expect(app_page.locator("#vidUrl")).to_have_value("not a link")          # what you typed stays


def test_rig_new_pedals_how_it_works_stack_and_recipes(app_page):
    onboarded(app_page)
    go(app_page, "rig")                                                       # the rig stays off: nothing plays
    app_page.locator("[data-add=pedals]").click()
    for name in ["Optical compressor", "Mid-hump drive", "Octave-up fuzz", "Envelope filter", "Rotary speaker", "Ring modulator"]:
        expect(app_page.locator("#fxDialog .pick", has_text=name)).to_be_visible()
    app_page.locator("#fxDialog .pick", has_text="Mid-hump drive").click()
    pedal = app_page.locator("#sec-pedals .pedal.stomp", has_text="Mid-hump drive")
    pedal.locator('[data-act="how"]').click()
    expect(app_page.locator("#fxDialog")).to_contain_text("asymmetric")
    expect(app_page.locator("#fxDialog .clip-plot")).to_have_count(4)          # this pedal + soft/hard/asym
    app_page.keyboard.press("Escape")
    app_page.locator(".stack-box summary").click()
    expect(app_page.locator("#stackCurve svg.stack-curve path")).to_be_visible()
    app_page.locator("#capForm button[type=submit]").click()
    expect(app_page.locator("#capErr")).to_contain_text("both recordings")
    go(app_page, "chart/01-em-am")
    sel = app_page.locator(".sec-row [data-preset]").first
    sel.select_option("factory:blues_crunch")
    expect(app_page.locator(".sec-row .recipe-chain").first).to_contain_text("Tweed")
    expect(app_page.locator(".sec-row [data-load]").first).to_be_visible()


def test_new_pedals_render_offline(app_page):
    """Every new pedal builds and passes signal (rendered offline: nothing reaches the speakers)."""
    onboarded(app_page)
    go(app_page, "home")
    out = app_page.evaluate("""async () => {
      const { EFFECTS } = await import('/static/lib/rig/effects.js');
      const ids = ['opto_comp', 'transparent', 'asym_drive', 'octave_fuzz', 'envelope', 'ring_mod', 'rotary', 'harmonic_trem', 'capture'];
      const res = {};
      for (const id of ids) {
        const ctx = new OfflineAudioContext(2, 22050, 44100);
        await ctx.audioWorklet.addModule('/static/lib/rig/worklets.js');
        const params = Object.fromEntries(EFFECTS[id].params.map(p => [p.id, p.def]));
        const fx = EFFECTS[id].build(ctx, params);
        const osc = ctx.createOscillator(); osc.frequency.value = 196;
        const g = ctx.createGain(); g.gain.value = 0.3;
        osc.connect(g).connect(fx.input); fx.output.connect(ctx.destination);
        osc.start();
        const buf = await ctx.startRendering();
        const d = buf.getChannelData(0);
        let peak = 0, finite = true;
        for (const v of d) { if (!Number.isFinite(v)) finite = false; peak = Math.max(peak, Math.abs(v)); }
        res[id] = { peak, finite };
      }
      return res;
    }""")
    for pid, r in out.items():
        assert r["finite"] and r["peak"] > 0.001, (pid, r)


def test_nothing_starts_on_its_own(app_page):
    """Settings and progress come back on reload, but nothing starts listening or playing by itself."""
    onboarded(app_page)
    started = []
    app_page.on("request", lambda r: "/api/live/start" in r.url and started.append(r.url))
    for route in ["rig", "lesson/major-scale?ex=g-position", "stage?chart=01-em-am", "tools?tab=metronome", "home"]:
        go(app_page, route)
        app_page.wait_for_timeout(400)
        app_page.reload()
        app_page.wait_for_timeout(400)
    assert started == []
    go(app_page, "rig")
    expect(app_page.locator("#rigPower")).to_have_attribute("aria-pressed", "false")


def test_dock_keys_course_peek_and_sources(app_page):
    onboarded(app_page)
    go(app_page, "home")
    app_page.locator("#dockToggle").click()
    expect(app_page.locator("body")).to_have_class(re.compile("nav-dock"))
    app_page.reload()
    expect(app_page.locator("body")).to_have_class(re.compile("nav-dock"))     # remembered in this browser
    app_page.locator("#dockToggle").click()
    app_page.keyboard.press("?")
    expect(app_page.locator("#keysDialog")).to_contain_text("Stage mode")
    app_page.keyboard.press("Escape")
    go(app_page, "course")
    row = app_page.locator(".lesson-row").first
    row.locator("summary").click()
    expect(row.locator(".lesson-peek")).to_contain_text("Play the 6 open strings")
    expect(app_page).to_have_url(re.compile("#/course"))                       # opened in place
    go(app_page, "settings")
    expect(app_page.locator("#sSources")).to_contain_text("Data folder")
    expect(app_page.locator("#sSources")).to_contain_text("default")


def test_practice_states_and_next_step(app_page):
    onboarded(app_page)
    _fake_listener(app_page, {"award": {"passed": True, "need": 80, "xp": 15, "next": {"code": "less_help", "params": {"level": 1}}},
                              "summary": {"score": 92}})
    go(app_page, "lesson/major-scale?ex=g-position")
    focus = app_page.locator("dialog.ex-focus")
    expect(focus.locator("#fState")).to_have_text("ready")
    app_page.keyboard.press(" ")
    expect(focus.locator("#fState")).to_have_text("playing")
    app_page.keyboard.press(" ")
    expect(focus.locator("#fState")).to_have_text("feedback")
    expect(focus.locator(".f-next")).to_contain_text("less help")
    focus.locator(".f-next button").click()
    expect(focus.locator('#fGuide button[data-g="1"]')).to_have_attribute("aria-pressed", "true")


def test_tab_order_follows_the_setting(app_page):
    """The 6th string is the top line by default; switching in Settings flips every tab and the fretboard."""
    onboarded(app_page)
    go(app_page, "lesson/reading-tab")
    tab = app_page.locator("pre.tab").first
    expect(tab).to_be_visible()
    assert tab.inner_text().splitlines()[0].startswith("E|")
    assert tab.inner_text().splitlines()[-1].startswith("e|")
    go(app_page, "settings")
    app_page.locator("#iTabOrder").select_option("high")
    expect(app_page.locator("#iStatus")).to_contain_text("saved")
    go(app_page, "lesson/reading-tab")
    lines = app_page.locator("pre.tab").first.inner_text().splitlines()
    assert lines[0].startswith("e|") and lines[-1].startswith("E|")
    assert "6:0" not in lines[0]
    assert lines[-1].startswith("E|-0")                        # the lick starts on the open 6th string, now at the bottom


def test_chart_practice_shows_bars_and_what_each_mode_expects(app_page):
    """A chart's columns are bars: the hint says how many beats, and what Wait and Tempo expect."""
    onboarded(app_page)
    go(app_page, "practice?chart=01-em-am")
    hint = app_page.locator("#laneHint")
    app_page.locator('#pMode button[data-mode="wait"]').click()
    expect(hint).to_contain_text("one bar of 4 beats")
    expect(hint).to_contain_text("choose Tempo")
    app_page.locator('#pMode button[data-mode="tempo"]').click()
    expect(hint).to_contain_text("↓ ↓ ↓ ↓")
    app_page.locator("#pChartClear").click()
    expect(hint).to_be_hidden()
