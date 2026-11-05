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
