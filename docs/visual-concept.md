# Visual concept: the lighthouse

Recorded 21 September 2026 from a conversation, before any front end
exists. Ideas, not decisions.

## The image

A lighthouse across the water from San Francisco, looking at the city.
Point Bonita on the Marin Headlands is the real one that faces the Golden
Gate with the skyline behind it. The index watches where AI is made from
the far shore. Fog on the water; the lantern lit after dusk on real local
time.

## Why it fits the index rather than decorating it

The index's central test is a beam sweeping over fog. Each release asks
whether anything has appeared in realised pay, employment or the training
pipeline, and publishes how strong a signal would have to be before it
could be seen. Fog is the noise, the beam is the test, and something
showing up in the light is detection. The side of the scene for "what has
moved" stays foggiest because nothing has crossed the threshold; the day
it thins is the story.

## Three beams, three layers

- Where usage lands: the water and the shipping lanes.
- What has moved: the city, pay and jobs.
- The pipeline: the bridge and the shore, who arrives and from where.

Hover sweeps the beam to a sector and clears the fog in the cone; the
title stays fixed and the details fade in beneath it. Click moves the
camera to the lantern room looking out at that sector, with the other two
sectors as labelled edges to turn towards. A panoramic image with a
perspective transform is the cheap version and works on a phone; a 3D
scene is the expensive one.

## Weather

Live San Francisco conditions from the National Weather Service API,
KSFO observations, no key needed: visibility, sky cover, wind. Fog is
procedural noise whose density follows the visibility reading and the
hour. Two toggles, labelled plainly, one for live weather and one for the
fog.

## Rules so the frame does not eat the content

1. Weather never encodes data. The only fog that carries meaning is the
   clearing on hover, which is interaction, not measurement. A footnote
   says the weather is live and decorative.
2. The three titles and one number each must read in three seconds with
   every effect off. Build that page first; the lighthouse rises around it.
3. The index needs its own name; "Lighthouse" is taken by a Google tool
   and stays the image only.

## Decisions taken in the second pass, 21 September 2026

- Turning is a pan across one drawn panorama, not a cut; the foreground
  moves faster than the skyline.
- The coin viewer rises into frame before the valley opens in its
  eyepieces, and its slot is the control for the sources card.
- Sources are drawn as kinds of institution, never as a company's
  building: a civic dome, a campanile, glass blocks on the shore. Names go
  in the text.
- One splash of colour per view, as a watercolour mark over one building:
  the bridge's orange, the dome's gold, the house over the green, the
  Ferry Building's white, a grey on the tallest tower, sandstone on Hoover
  Tower. No hover on any of them; they are there to be seen.
- Weather has a vocabulary of eight states drawn from the observation, not
  a forecast, so the sky is right in kind rather than in every detail.
- The name is still open.

## Third pass, 21 September 2026: the sky is the observation

- No menu. The KSFO observation picks the preset, and wind and rain set
  the two dials. The observation time is shown; a stale one says so.
- Motion follows the wind by the heading of the view: a westerly moves
  nothing sideways at the point, pours fog through the Gate at the bridge,
  slides cloud across at the city. Calm defaults to the westerly.
- The light follows San Francisco's clock, not the visitor's device: sun
  by a solar formula at the headland, dawn and dusk as one warm band,
  night as white ink on black with the lantern lit, the moon at its phase.
- Three rules hold: nothing moves faster than a cloud; one wash per view
  plus the sky's band at the two ends of the day; the numbers never change
  with the weather.
