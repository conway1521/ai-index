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
