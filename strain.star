load("render.star", "render")

DEFAULT_STRAIN = "14.2"
DEFAULT_FIRST_NAME = "Michael"
MAX_STRAIN = 21.0
WIDTH = 64
BAR_HEIGHT = 3
BAR_BG = "#333333"
LABEL_COLOR = "#AAAAAA"
NAME_COLOR = "#B0B0B0"

ZONE_LIGHT = "#1E90FF"
ZONE_MODERATE = "#00C853"
ZONE_HIGH = "#FF9800"
ZONE_ALL_OUT = "#F44336"

def format_one_decimal(x):
    tenths = int(x * 10 + 0.5)
    return "%d.%d" % (tenths // 10, tenths % 10)

def zone_color(strain):
    if strain < 10:
        return ZONE_LIGHT
    elif strain < 14:
        return ZONE_MODERATE
    elif strain < 18:
        return ZONE_HIGH
    else:
        return ZONE_ALL_OUT

def main(config):
    raw = config.str("strain", DEFAULT_STRAIN)
    if raw == "":
        raw = DEFAULT_STRAIN
    first_name = config.str("first_name", DEFAULT_FIRST_NAME)
    if first_name == "":
        first_name = DEFAULT_FIRST_NAME
    strain = float(raw)
    if strain < 0:
        strain = 0.0
    if strain > MAX_STRAIN:
        strain = MAX_STRAIN

    color = zone_color(strain)
    fill_w = int(strain / MAX_STRAIN * WIDTH)
    if strain > 0 and fill_w < 1:
        fill_w = 1

    bar_children = [render.Box(width = WIDTH, height = BAR_HEIGHT, color = BAR_BG)]
    if fill_w > 0:
        bar_children.append(render.Box(width = fill_w, height = BAR_HEIGHT, color = color))

    return render.Root(
        child = render.Column(
            expanded = True,
            main_align = "space_between",
            cross_align = "center",
            children = [
                render.Column(
                    cross_align = "center",
                    children = [
                        render.Text(content = "WHOOP STRAIN", font = "tom-thumb", color = LABEL_COLOR),
                        render.Text(content = first_name, font = "tom-thumb", color = NAME_COLOR),
                    ],
                ),
                render.Text(content = format_one_decimal(strain), font = "6x13", color = color),
                render.Stack(children = bar_children),
            ],
        ),
    )
