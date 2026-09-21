# Front page mockup

`index.html` is a self-contained page: open it in a browser. It is the
lighthouse concept from `docs/visual-concept.md` drawn in black ink on
paper, with three views (the city, the bridge, the telescope to the
valley), a coin viewer for sources and method, and the readings from the
20 September 2026 build beneath the drawing.

The weather is drawn into the scene. Fog thickness follows visibility, the
fog drifts with the wind, cloud and rain are drawn when reported. In
production the conditions come from the National Weather Service's latest
observation at KSFO, no key needed:

    https://api.weather.gov/stations/KSFO/observations/latest

The mockup cannot reach that host and draws a sample observation, labelled
as such. The name on the page is a placeholder.
