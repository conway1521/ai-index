# Front page mockup

`index.html` is a self-contained page: open it in a browser. It is the
lighthouse concept from `docs/visual-concept.md` drawn in black ink on
paper with one splash of colour in each view.

What it does:

- One panorama, three screens wide: the bridge, the point, the city. Turning
  slides the viewport across it, with the lighthouse and railing on a
  foreground layer that moves faster, so a turn reads as turning your head.
- The coin viewer rises into the lower frame when the telescope is chosen,
  eyepieces first, and the valley opens in the two circles above it. The
  coin slot on its face opens the sources card.
- The sources card carries three buildings, one per kind of source: the
  civic dome for the statistical agencies, the campanile for the training
  pipeline, the glass blocks on the shore for usage. Real names sit in the
  text beneath, never on the buildings.
- Colour: the bridge in its orange; the dome in gold, the house over the
  green in rose, the green itself; the Ferry Building off-white; one grey
  wash on the tallest tower; Hoover Tower's sandstone in the valley.
- The sky is the latest observation at KSFO
  (https://api.weather.gov/stations/KSFO/observations/latest), no menu:
  the description and visibility pick one of eight presets, wind sets the
  drift speed and direction of fog and cloud by the heading of the view
  (the point looks east, the bridge south, the city north-east), rain
  falls slanted by it, gulls lean in it. The page fetches on load and
  every ten minutes, shows the observation time, and says "last
  observation" when it is stale. The mockup cannot reach the host and
  draws a sample observation, labelled as such.
- The light follows San Francisco's clock: the sun's position from a
  solar formula at the headland, rising over the city and setting past the
  bridge; a warm band on the horizon at dawn and dusk; white ink on black
  after dark with the lantern lit; the moon at its phase from lunar age.
- For testing, the URL can force a sky and an hour:
  `?sky=storm&hour=23&wind=270,40`. Presets: clear, light cloud, overcast,
  fog, thick fog, rain, heavy rain, wind, storm.

The captures are from a 1280-pixel window: dawn over the city, fog at
the bridge with a westerly, night at the point, a storm. The name on the page is a
placeholder.
