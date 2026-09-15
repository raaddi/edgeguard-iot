"""SVG floor plan based on the supplied model photographs (not a measured CAD plan)."""

from html import escape


def floorplan(sim, selected="garage"):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 780" role="img" '
             'aria-label="Makieta SmartHome: pomieszczenia, oświetlenie, czujniki, wentylatory i bramy" '
             'style="width:100%;max-height:720px;display:block">',
             '<defs><pattern id="tiles" width="25" height="25" patternUnits="userSpaceOnUse">'
             '<path d="M25 0H0V25" fill="none" stroke="#ffffff" opacity=".04"/></pattern></defs>',
             '<rect x="18" y="12" width="724" height="750" rx="20" fill="#101f2c"/>']

    def text(x, y, value, size=15, color="#c9d9e7"):
        parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="sans-serif" font-size="{size}">{escape(str(value))}</text>')

    def rect(x, y, w, h, fill, stroke="#314654", radius=0):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')

    for room in sim.profile["rooms"]:
        rid = room["id"]
        x, y, w, h = room["rect"]
        components = [c for c in sim.components.values() if c["room"] == rid]
        lights = [c for c in components if c["kind"] == "light"]
        lit = any(sim.actuators[c["id"]]["simulated"] for c in lights)
        fill = "#263930" if rid == "yard" else "#343b30" if lit else "#172c3c"
        rect(x, y, w, h, fill, "#61e3c2" if rid == selected else "#567081")
        rect(x+3, y+3, w-6, h-6, "url(#tiles)", "none")
        text(x+14, y+26, room["name"], 16 if rid != "room" else 13, "#f0f5fa")
        node = sim.room_nodes[rid]
        text(x+14, y+45, node.replace("esp32_node_", "węzeł "), 11, "#8ea7bc" if sim.nodes[node] else "#fb9f86")
        if rid == "yard":
            rect(70, 590, 190, 125, "#514a34", "none", 5)
            rect(310, 590, 90, 125, "#514a34", "none", 5)
        for i, light in enumerate(lights):
            lx = x + 24 + i * 43
            ly = y + h - 25
            on = sim.actuators[light["id"]]["simulated"]
            if on:
                parts.append(f'<circle cx="{lx}" cy="{ly}" r="24" fill="#ffdd83" opacity=".13"/>')
            parts.append(f'<circle cx="{lx}" cy="{ly}" r="8" fill="{"#ffdd83" if on else "#485c6b"}" stroke="#81929e"/>')
            text(lx+12, ly+4, light["id"].replace("led_", "L"), 10)
        for c in components:
            if c["kind"] == "gas":
                value = sim.sensors[c["id"]]["value"]
                color = "#ffb69e" if value > sim.profile["threshold"] else "#61e3c2"
                rect(x+12, y+53, min(145, w-24), 26, "#0c1a26", "none", 6)
                text(x+20, y+71, f"G{c['id'][-2:]}  {value:.3f}", 14, color)
            if c["kind"] == "fan":
                active = sim.actuators[c["id"]]["simulated"]
                fx, fy = x+w-29, y+30
                color = "#61e3c2" if active else "#8193a0"
                angle = (sim.time * 40) % 360 if active else 0
                parts.append(f'<g transform="translate({fx},{fy}) rotate({angle})" stroke="{color}" fill="none" stroke-width="3">'
                             '<circle r="16"/><path d="M-11 0H11M0 -11V11"/><circle r="3"/></g>')
                text(x+w-47, y+58, "ON" if active else "OFF", 10, color)

    # Simple furnishings and driveway keep the orientation recognisable.
    rect(462, 144, 210, 28, "#294252", "#54707e", 4)
    rect(639, 177, 33, 74, "#294252", "#54707e", 4)
    parts.append('<circle cx="491" cy="157" r="8" fill="none" stroke="#96adba"/>'
                 '<circle cx="518" cy="157" r="8" fill="none" stroke="#96adba"/>')
    rect(111, 407, 94, 75, "#243b49", "#6a8798", 15)
    rect(121, 422, 74, 27, "#122330", "#6a8798", 5)
    text(126, 468, "AUTO", 13)
    rect(478, 378, 183, 80, "#294252", "#54707e", 8)
    rect(489, 389, 47, 29, "#435d6d", "none", 5)
    rect(604, 389, 47, 29, "#435d6d", "none", 5)
    text(110, 634, "PODJAZD", 14, "#d9c69e")
    text(488, 634, "OGRÓD", 14, "#a6ccab")
    for cid, item in sim.components.items():
        if item["kind"] != "servo":
            continue
        x1, y1, x2, y2 = item["line"]
        opened = sim.actuators[cid]["simulated"] > 0
        parts.append(f'<path d="M{x1} {y1}L{x2} {y2}" stroke="#0c1420" stroke-width="10"/>')
        ex, ey = (x1, y1-abs(x2-x1)*0.75) if opened else (x2,y2)
        color = "#61e3c2" if opened else "#d5b782"
        parts.append(f'<path d="M{x1} {y1}L{ex} {ey}" stroke="{color}" stroke-width="6" stroke-linecap="round"/>')
        text(min(x1,x2)+8, y1-12, cid.replace("servo_", "S"), 11, color)
    text(50, 752, "FRONT MAKIETY  ·  WJAZD I FURTKA", 11, "#89a1b3")
    parts.append('</svg>')
    return "".join(parts)
