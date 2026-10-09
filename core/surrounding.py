"""The surrounding area of ENVI-met 6 (the surroundingArea section of the INX).

ENVI-met 6 describes the land outside each of the four model borders by one of 27
urban or land-cover types. The INX stores their position in this list; older
ENVI-met versions ignore the section.

The borders are named in grid terms: left = the -x side, right = +x, front = -y,
rear = +y. Under a model rotation they face other compass directions, which the
plugin shows next to them.

No QGIS imports.
"""

# In the order ENVI-met stores them (do not sort)
TYPES = [
    'Compact high-rise', 'Compact mid-rise', 'Compact low-rise',
    'Open high-rise', 'Open mid-rise', 'Open low-rise',
    'Lightweight low-rise', 'Large low-rise', 'Sparsely built', 'Heavy industry',
    'European perimeter block', 'Open row housing', 'Historic dense core / old town',
    'Dense high-rise residential (tower blocks)', 'Dense low-rise vernacular (shophouse / hutong)',
    'Downtown high-rise core (CBD)', 'Detached suburban housing', 'Urban park / green space',
    'Dense trees / forest', 'Scattered trees', 'Bush, scrub', 'Low plants / grassland', 'Cropland / agriculture',
    'Wetland / marsh', 'Bare soil or sand', 'Bare rock or paved', 'Open water',
]
DEFAULT_TYPE = 1   # compact mid-rise, ENVI-met's default for every border

BORDERS = ('Left', 'Right', 'Front', 'Rear')

_COMPASS = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west']


def border_bearings(rotation):
    """Bearing (degrees clockwise from north) each border faces, for the INX model rotation."""
    return {'Left': (270.0 + rotation) % 360.0, 'Right': (90.0 + rotation) % 360.0,
            'Front': (180.0 + rotation) % 360.0, 'Rear': rotation % 360.0}


def compass(bearing):
    return _COMPASS[int(((bearing % 360.0) + 22.5) // 45.0) % 8]


def rotation_from_bearing(bearing_lower_edge):
    """INX model rotation from the bearing of the model's lower edge (lower-left to lower-right corner)."""
    rotation = (bearing_lower_edge - 90.0) % 360.0
    return rotation - 360.0 if rotation > 180.0 else rotation


def border_labels(rotation=None):
    """Label per border, with the compass direction it faces when the rotation is known."""
    if rotation is None:
        return {border: f'{border} border:' for border in BORDERS}
    bearings = border_bearings(rotation)
    return {border: f'{border} border (faces {compass(bearings[border])}):' for border in BORDERS}


def section(use, borders):
    """The INX surroundingArea values. ``borders`` maps Left/Right/Front/Rear to a type index."""
    values = {'useSurroundingArea': bool(use)}
    for border in BORDERS:
        index = int(borders.get(border, DEFAULT_TYPE))
        if not 0 <= index < len(TYPES):
            index = DEFAULT_TYPE
        values[f'border{border}'] = index
    return values
