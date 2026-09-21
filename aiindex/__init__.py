"""A public index of where AI usage has reached the labour market.

Three layers, each in its own units and never composited: a national layer
that maps observed AI usage into the wage bill and tests realised wages and
employment against a stated detection threshold; a state layer at annual
cadence carrying exposure, adoption and capacity; and a pipeline and
capacity layer that sizes arrivals from education against arrivals from
other occupations.

The package imports the paper's own machinery from ``src`` for the pieces
that already exist there, the O*NET readers, the gamma construction, the
named bundles and the relabelling inference, and adds only what the index
needs on top. Every number it writes carries a manifest entry naming the
file it came from and whether that file was the official release or a
fixture standing in for it.
"""
