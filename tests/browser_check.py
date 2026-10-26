"""Optional end-to-end checks. Run a local app first; see README for setup."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def check(url: str, screenshot_dir: str | None = None) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1060}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(url, wait_until="networkidle")
        assert response.status == 200, "Home page did not open"
        page.wait_for_function("document.getElementById('mapLoading').hidden")
        frame = page.frame_locator("#mapFrame")
        map_frame = page.locator("#mapFrame").element_handle().content_frame()
        map_frame.wait_for_function("Boolean(window.AtlasMap)")
        species = page.evaluate("JSON.parse(document.getElementById('atlasData').textContent).species")
        assert len(species) == page.locator(".species-row").count()
        assert map_frame.evaluate("ATLAS_MAP_CONFIG.map.getZoom()") >= 3
        if screenshot_dir:
            out = Path(screenshot_dir)
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / "desktop.png"), full_page=True)

        for item in species:
            page.locator(f"[data-species='{item['id']}']").click()
            visible = map_frame.evaluate("""() => Object.entries(ATLAS_MAP_CONFIG.groups)
                .filter(([id, group]) => ATLAS_MAP_CONFIG.map.hasLayer(group)).map(([id]) => id)""")
            assert visible == [item["id"]], f"Filter failed for {item['name']}"
            assert str(item["count"]) in page.locator("#visibleCount").inner_text()

        photo_species = next(item for item in species if item["thumbnail"])
        page.locator(f"[data-species='{photo_species['id']}']").click()
        page.wait_for_timeout(500)  # Let Leaflet finish fitting before opening a point.
        map_frame.evaluate("""() => { const c=ATLAS_MAP_CONFIG; c.markers.find(m=>c.map.hasLayer(c.groups[m.speciesId])).layer.fire('click'); }""")
        frame.locator(".observation-popup").wait_for()
        frame.locator(".observation-photo img").wait_for()
        assert frame.locator(".observation-photo figcaption").inner_text() == "Representative species photo"
        frame.locator(".observation-photo img").evaluate("image => image.decode()")
        if screenshot_dir:
            page.screenshot(path=str(out / "plant-popup.png"), full_page=True)

        no_photo = next(item for item in species if not item["thumbnail"])
        page.locator(f"[data-species='{no_photo['id']}']").click()
        map_frame.evaluate("""() => { const c=ATLAS_MAP_CONFIG; c.markers.find(m=>c.map.hasLayer(c.groups[m.speciesId])).layer.fire('click'); }""")
        assert frame.locator(".observation-popup").count() == 1
        assert frame.locator(".observation-photo").count() == 0

        page.locator("#allSpecies").click()
        map_frame.evaluate("""() => { const c=ATLAS_MAP_CONFIG; const marker=c.markers.find(m=>c.locations[m.locationId].length>1); marker.layer.fire('click'); }""")
        first = frame.locator(".observation-source").inner_text()
        frame.get_by_role("button", name="Next observation at this location").click()
        assert frame.locator(".observation-source").inner_text() != first

        page.locator("#speciesSearch").fill("no-such-plant-123")
        assert page.locator("#emptySearch").is_visible()
        page.locator("#resetSearch").click()
        assert page.locator(".species-row:visible").count() == len(species)
        page.locator("#speciesSearch").fill(photo_species["scientific_name"])
        assert page.locator(f"[data-species='{photo_species['id']}']").is_visible()
        page.locator("#clearSearch").click()
        page.locator("#speciesSort").select_option("count")
        assert int(page.locator(".species-row").first.get_attribute("data-count")) == max(s["count"] for s in species)
        page.locator("#speciesSort").select_option("az")
        page.locator("[data-basemap=satellite]").click()
        assert map_frame.evaluate("ATLAS_MAP_CONFIG.map.hasLayer(ATLAS_MAP_CONFIG.basemaps.satellite)")
        page.locator("[data-basemap=street]").click()
        page.locator("#legendToggle").click()
        assert page.locator(".legend-item").count() == len(species)
        page.locator("#legendToggle").click()
        page.locator("[data-open-about]").first.click()
        assert page.locator("#aboutDialog").is_visible()
        page.keyboard.press("Escape")
        assert not page.locator("#aboutDialog").is_visible()
        page.locator("#allSpecies").click()
        page.locator("#fullscreenMap").click()
        page.wait_for_function("Boolean(document.fullscreenElement || document.getElementById('mapPanel').classList.contains('expanded'))")
        page.locator("#fullscreenMap").click()
        page.wait_for_function("!document.fullscreenElement && !document.getElementById('mapPanel').classList.contains('expanded')")

        # Local library assets keep geometry usable even when tile services fail.
        page.route("https://**/*", lambda route: route.abort())
        page.reload(wait_until="networkidle")
        page.wait_for_function("document.getElementById('mapLoading').hidden")
        map_frame = page.locator("#mapFrame").element_handle().content_frame()
        assert map_frame.evaluate("Boolean(window.AtlasMap)")
        page.unroute("https://**/*")

        page.set_viewport_size({"width": 390, "height": 844})
        page.reload(wait_until="networkidle")
        page.wait_for_function("document.getElementById('mapLoading').hidden")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile horizontal overflow"
        page.locator(f"[data-species='{photo_species['id']}']").click()
        page.locator("#mapPanel").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        map_frame = page.locator("#mapFrame").element_handle().content_frame()
        map_frame.evaluate("""() => { const c=ATLAS_MAP_CONFIG; c.markers.find(m=>c.map.hasLayer(c.groups[m.speciesId])).layer.fire('click'); }""")
        frame.locator(".observation-photo img").evaluate("image => image.decode()")
        map_frame.wait_for_function("""() => {const r=document.querySelector('.leaflet-popup').getBoundingClientRect(); return r.top >= -1 && r.bottom <= innerHeight+1;}""")
        assert page.locator("#mapStage").evaluate("element => element.classList.contains('has-popup')")
        page.evaluate("document.activeElement.blur()")
        if screenshot_dir:
            page.screenshot(path=str(out / "mobile.png"), full_page=True)
        for width in (320, 768, 1920):
            page.set_viewport_size({"width": width, "height": 960})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Horizontal overflow at {width}px"
        assert not errors, json.dumps(errors)
        print(f"Browser checks passed: {len(species)} filters, photos, shared locations, search, sort, layers, legend, dialog, fullscreen, offline geometry, 320-1920px layouts; no JS errors.")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5055")
    parser.add_argument("--screenshots", help="Optional folder for desktop, popup, and mobile screenshots")
    args = parser.parse_args()
    check(args.url, args.screenshots)
