"""End-to-end flows through the web UI."""
import re

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


def test_rig_effects_and_presets(app_page):
    onboarded(app_page)
    go(app_page, "rig")
    expect(app_page.get_by_role("heading", name="Amp & effects")).to_be_visible()
    before = app_page.locator("#sec-pedals .pedal[data-uid]").count()
    app_page.locator("[data-add=pedals]").click()
    app_page.locator("#fxDialog .pick", has_text="Fuzz").click()
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
    expect(app_page.locator("#neck")).to_have_attribute("viewBox", "0 0 1000 274")       # 7 strings
    go(app_page, "chords")
    expect(app_page.locator(".callout", has_text="standard tuning")).to_be_visible()
    label = app_page.locator(".chord-card").first.locator("svg text").last
    expect(label).to_have_text("E  B  G  D  A  E")                                      # mirrored


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
