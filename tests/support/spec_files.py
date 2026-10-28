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

#: Conventions of other acquisition programs and SPEC versions: Bluesky header
#: (empty motor lines, ``None`` values, ``#MD`` metadata), labels separated by
#: single spaces, several MCA devices with their own calibration, other ``@``
#: lines, and an interrupted mesh scan
MORE_TEXT = """\
#F bluesky.spec
#E 1792483200
#D Tue Oct 20 12:00:00 2026
#C Bluesky  user = test
#O0\x20
#o0\x20

#S 1 count(detectors=['scaler'])
#D Tue Oct 20 12:01:00 2026
#T 0.5  (seconds)
#M 1000  (I0)
#Q 1 0 0.5
#G0 0 0 1 2
#MD uid = 1234-abcd
#N 4
#L Epoch seconds I0 diode
1.5 0.5 1000 None
2.5 0.5 1001 12
#C Scan ended normally.

#S 2 ascan en 690 692 2 1
#D Tue Oct 20 12:02:00 2026
#N 3
#L Energy  I0  TEY
#@CALIB 0 1 0
#@CALIB 1 2 0 mca2
#@CHANN 4 0 3 1 mca2
690 100 5
@A1 1 2 3 4
@A2 5 6 7 8
691 101 6
@A1 2 3 4 5
@A2 6 7 8 9
692 102 7
@A1 3 4 5 6
@A2 7 8 9 10
@0 0 0 0 0 0 0 0 0\\
 1 1 1 1

#S 3 mesh  samx 0 2 2  samy 11 10 1  1
#D Tue Oct 20 12:03:00 2026
#N 3
#L Sample X  Sample Y  counts
0 11 1
1 11 2
2 11 3
0 10 4
1 10 5
"""

#: Mesh scans of 2 rows of 3 points (counts 1 to 6 in acquisition order) with
#: data lines that cannot be read: a lost point (1.1), a line holding no point
#: (2.1), a lost point at the end of a row with a decreasing second motor and a
#: position off the grid by 0.3 step (3.1), two points written on one line
#: (4.1), a lost first point (5.1, ``mesh``; 6.1, ``dmesh``), and a lost line
#: followed by positions half a step off the grid, which fit no number of
#: missing points (7.1)
MESH_TEXT = """\
#F mesh.spec
#E 1792483200
#D Tue Oct 20 13:00:00 2026

#S 1 mesh  samx 0 2 2  samy 10 11 1  1
#N 3
#L samx  samy  counts
0 10 1
1 10 oops
2 10 3
0 11 4
1 11 5
2 11 6

#S 2 mesh  samx 0 2 2  samy 10 11 1  1
#N 3
#L samx  samy  counts
0 10 1
1 10 2
Scan paused by user
2 10 3
0 11 4
1 11 5
2 11 6

#S 3 mesh  samx 0 2 2  samy 11 10 1  1
#N 3
#L samx  samy  counts
0 11 1
1 11 2
2 11
0.3 10 4
1 10 5
2 10 6

#S 4 mesh  samx 0 2 2  samy 10 11 1  1
#N 3
#L samx  samy  counts
0 10 1
1 10 2
2 10 3 0 11 4
1 11 5
2 11 6

#S 5 mesh  samx 0 2 2  samy 10 11 1  1
#N 3
#L samx  samy  counts
0 10
1 10 2
2 10 3
0 11 4
1 11 5
2 11 6

#S 6 dmesh  samx 0 2 2  samy 10 11 1  1
#N 3
#L samx  samy  counts
0 10
1 10 2
2 10 3
0 11 4
1 11 5
2 11 6

#S 7 mesh  samx 0 2 2  samy 10 11 1  1
#N 3
#L samx  samy  counts
0 10 1
1 10 oops
1.5 10 3
0.5 11 4
1.5 11 5
2.5 11 6
"""


def write_spec(path: Path, newline: str = "\n", text: str = SPEC_TEXT) -> str:
    """Write a synthetic SPEC file and return its name.

    SPEC writes ``\\n`` line endings; ``newline`` lets tests check others.
    """
    with open(path, "w", encoding="latin-1", newline=newline) as file:
        file.write(text)
    return str(path)
