"""Synthetic SPEC files covering the conventions read by the plugin."""

from __future__ import annotations

from pathlib import Path

SPEC_TEXT = """\
#F synthetic.spec
#E 1792483200
#D Tue Oct 20 10:00:00 2026
#C test file
#O0 th  tth  sample z

#S 1 ascan  th 1 0.6 4 0.1
#D Tue Oct 20 10:01:00 2026
#T 0.1  (Seconds)
#P0 1.0 2.5 -0.25
#N 3
#L Theta  Monitor  Detector counts
1.0 1000 10
0.9 1001 25
0.8 999 60
0.7 1002 24
0.6 1000 11

#S 1 ascan  th 0 1 2 0.1
#D Tue Oct 20 10:05:00 2026
#P0 0.0 2.5 -0.25
#N 3
#L Theta  Monitor  Detector counts
0.0 500 1
0.5 501 2
1.0 502 3

#S 2 timescan 0.5
#D Tue Oct 20 10:10:00 2026
#N 3
#L Time  I0  It
0 10 5
1 11 6
2 1
#C Tue Oct 20 10:10:03 2026.  Scan aborted after 2 points.

#S 3 ct 1
#D Tue Oct 20 10:20:00 2026
#N 1
#L Seconds
#@MCA 8C
#@CHANN 8 2 9 1
#@CALIB 0.5 0.25 0
1
@A 0 1 2 3 \\
 4 5 6 7

#F second.spec
#E 1792483300
#O0 energy  gap

#S 4 Escan 7.1 7.4 3 1
#D Tue Oct 20 11:00:00 2026
#P0 7.1 12.5
#N 3
#L Energy  I0  It
#@MCA 4C
7.1 100 50
@A 1 2 3 4
7.2 101 49
@A 2 3 4 5
7.4 102 47
@A 3 4 5 6
"""


def write_spec(path: Path, newline: str = "\n") -> str:
    """Write the synthetic SPEC file and return its name.

    SPEC writes ``\\n`` line endings; ``newline`` lets tests check others.
    """
    with open(path, "w", encoding="latin-1", newline=newline) as file:
        file.write(SPEC_TEXT)
    return str(path)
