"""Layer 3: one Report, several ways of showing it.

Plan §4.2. Every output the tool has -- the CLI tables, the CSV dumps, the JSON
the web view reads -- is a rendering of the same `Report`. This layer imports
neither `loader` nor `settle`, and that restriction is the whole point: it means
there is no path by which the terminal and the browser could disagree about what
a member owes. A rendering bug shows up in one place; a data bug shows up in all
of them at once.

    text    the CLI tables, CJK width alignment included
    sheets  CSV output
    web     the local HTTP service (Phase 1)
"""
