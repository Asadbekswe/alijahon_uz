"""
Deterministic studio-style product illustrations for development data.

Each image is rendered at 2x and downsampled for smooth edges: a soft tinted backdrop, a floor shadow
and a simple shaded silhouette of the product family (phone, bottle, bag, ...).
"""
import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter

SIZE = 900
SCALE = 2


def _hex(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _lighten(c, t):
    return _mix(c, (255, 255, 255), t)


def _darken(c, t):
    return _mix(c, (0, 0, 0), t)


def _tone(c, t):
    """Continuous light falloff across a surface: brighter on the lit side (t=0), darker on the far side."""
    v = .2 - .42 * t
    return _lighten(c, v) if v >= 0 else _darken(c, -v)


class Canvas:
    def __init__(self, background, seed):
        self.s = SIZE * SCALE
        self.rng = random.Random(seed)
        bg = _hex(background)
        self.img = Image.new('RGB', (self.s, self.s), bg)
        # soft radial light from the top-left
        glow = Image.new('L', (self.s, self.s), 0)
        ImageDraw.Draw(glow).ellipse((-self.s * .2, -self.s * .3, self.s * .9, self.s * .8), fill=150)
        glow = glow.filter(ImageFilter.GaussianBlur(self.s * .12))
        self.img = Image.composite(Image.new('RGB', self.img.size, _lighten(bg, .55)), self.img, glow)
        self.draw = ImageDraw.Draw(self.img)

    def u(self, v):
        return int(v * self.s / 100)

    def box(self, x0, y0, x1, y1):
        return tuple(self.u(v) for v in (x0, y0, x1, y1))

    def shadow(self, cx, cy, w, h, strength=90):
        layer = Image.new('L', self.img.size, 0)
        ImageDraw.Draw(layer).ellipse(self.box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), fill=strength)
        layer = layer.filter(ImageFilter.GaussianBlur(self.u(2.2)))
        self.img.paste((0, 0, 0), mask=layer.point(lambda p: int(p * .55)))
        self.draw = ImageDraw.Draw(self.img)

    def shaded_rect(self, box, color, radius, vertical=False):
        """Rounded rectangle with a gentle left-to-right (or top-down) light falloff."""
        x0, y0, x1, y1 = self.box(*box)
        w, h = x1 - x0, y1 - y0
        grad = Image.new('RGB', (w, h))
        gd = ImageDraw.Draw(grad)
        steps = h if vertical else w
        for i in range(steps):
            t = i / max(steps - 1, 1)
            shade = _tone(color, t)
            if vertical:
                gd.line((0, i, w, i), fill=shade)
            else:
                gd.line((i, 0, i, h), fill=shade)
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=self.u(radius), fill=255)
        self.img.paste(grad, (x0, y0), mask)
        self.draw = ImageDraw.Draw(self.img)

    def shaded_ellipse(self, box, color):
        x0, y0, x1, y1 = self.box(*box)
        w, h = x1 - x0, y1 - y0
        grad = Image.new('RGB', (w, h))
        gd = ImageDraw.Draw(grad)
        for i in range(w):
            t = i / max(w - 1, 1)
            gd.line((i, 0, i, h), fill=_tone(color, t))
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, w - 1, h - 1), fill=255)
        self.img.paste(grad, (x0, y0), mask)
        self.draw = ImageDraw.Draw(self.img)

    def highlight(self, box, radius, alpha=70):
        layer = Image.new('L', self.img.size, 0)
        ImageDraw.Draw(layer).rounded_rectangle(self.box(*box), radius=self.u(radius), fill=alpha)
        layer = layer.filter(ImageFilter.GaussianBlur(self.u(.6)))
        self.img.paste((255, 255, 255), mask=layer)
        self.draw = ImageDraw.Draw(self.img)

    def finish(self):
        out = self.img.resize((SIZE, SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, 'JPEG', quality=86, optimize=True, progressive=True)
        return buf.getvalue()


# ---------------------------------------------------------------- product families

def draw_phone(c, color, variant):
    c.shadow(50, 86, 34, 5)
    c.shaded_rect((33, 12, 67, 86), _darken(color, .35), 6)
    c.shaded_rect((35, 14, 65, 84), (24, 26, 32), 5, vertical=True)
    screen = (36.5, 15.5, 63.5, 82.5)
    c.shaded_rect(screen, _lighten(color, .15), 4.4, vertical=True)
    c.draw.rounded_rectangle(c.box(45, 17, 55, 19.5), radius=c.u(1.2), fill=(15, 15, 18))
    for i, h in enumerate((18, 22, 12)):
        c.draw.rounded_rectangle(c.box(40, 30 + i * 14, 40 + h, 36 + i * 14), radius=c.u(1.5),
                                 fill=_lighten(color, .55))
    c.highlight((37.5, 16.5, 41, 60), 2, 45)


def draw_slab(c, color, variant):
    """Power bank, wallet, cutting board, yoga block."""
    wide = variant == 'wide'
    box = (22, 34, 78, 72) if wide else (30, 22, 70, 80)
    c.shadow(50, box[3], (box[2] - box[0]) * 1.05, 5)
    c.shaded_rect(box, color, 5)
    c.shaded_rect((box[0] + 3, box[1] + 3, box[2] - 3, box[1] + 9), _lighten(color, .18), 3)
    c.draw.ellipse(c.box(box[2] - 9, box[3] - 9, box[2] - 5, box[3] - 5), fill=_lighten(color, .6))
    c.highlight((box[0] + 2, box[1] + 2, box[0] + 6, box[3] - 8), 2, 40)


def draw_bottle(c, color, variant):
    """Perfume / serum / shampoo / water bottle."""
    if variant == 'perfume':
        c.shadow(50, 83, 38, 5)
        c.shaded_rect((32, 38, 68, 83), _lighten(color, .1), 7)
        c.shaded_rect((36, 42, 64, 79), _lighten(color, .45), 5)
        c.shaded_rect((44, 28, 56, 39), (190, 160, 90), 2)
        c.shaded_rect((40, 16, 60, 29), (30, 30, 34), 3)
        c.draw.rounded_rectangle(c.box(40, 55, 60, 64), radius=c.u(1), fill=(250, 248, 242))
        c.highlight((35, 41, 38.5, 76), 2, 70)
        return
    tall = variant in ('tall', 'sport')
    top = 22 if tall else 30
    c.shadow(50, 86, 30, 5)
    c.shaded_rect((36, top + 12, 64, 86), color, 8)
    c.shaded_rect((43, top + 3, 57, top + 14), _darken(color, .1), 2)
    c.shaded_rect((41, top - 6, 59, top + 4), (40, 40, 46) if variant != 'sport' else _darken(color, .4), 2.5)
    c.draw.rounded_rectangle(c.box(39, top + 30, 61, top + 46), radius=c.u(1.5), fill=_lighten(color, .75))
    c.draw.rounded_rectangle(c.box(43, top + 35, 57, top + 37), radius=c.u(.6), fill=_darken(color, .2))
    c.highlight((38.5, top + 15, 41.5, 80), 2, 60)


def draw_jar(c, color, variant):
    c.shadow(50, 78, 50, 6)
    c.shaded_rect((26, 46, 74, 78), _lighten(color, .1), 6)
    c.shaded_rect((24, 34, 76, 48), _darken(color, .25), 3.5)
    c.draw.rounded_rectangle(c.box(34, 56, 66, 68), radius=c.u(1.5), fill=(252, 250, 246))
    c.draw.rounded_rectangle(c.box(39, 60.5, 61, 62.5), radius=c.u(.6), fill=_darken(color, .25))
    c.highlight((28, 49, 31.5, 74), 2, 55)


def draw_cylinder(c, color, variant):
    """Bluetooth speaker, candle, blender base, mug."""
    if variant == 'mug':
        c.shadow(46, 78, 46, 6)
        c.draw.rounded_rectangle(c.box(62, 42, 80, 66), radius=c.u(8), outline=_darken(color, .1), width=c.u(4.2))
        c.shaded_rect((24, 32, 66, 78), color, 6)
        c.draw.ellipse(c.box(24, 29, 66, 36), fill=_darken(color, .35))
        c.highlight((27, 36, 30.5, 72), 2, 60)
        return
    if variant == 'candle':
        c.shadow(50, 80, 44, 6)
        c.shaded_rect((30, 40, 70, 80), (238, 232, 222), 5)
        c.shaded_rect((30, 52, 70, 70), color, 0)
        c.draw.ellipse(c.box(30, 37, 70, 44), fill=(246, 242, 234))
        c.draw.line(c.box(50, 32, 50, 40), fill=(40, 40, 40), width=c.u(.8))
        c.draw.ellipse(c.box(47.5, 23, 52.5, 33), fill=(255, 190, 80))
        return
    c.shadow(50, 84, 42, 6)
    c.shaded_rect((30, 20, 70, 84), color, 18)
    for row in range(9):
        for col in range(6):
            x, y = 36 + col * 5.6, 32 + row * 4.4
            c.draw.ellipse(c.box(x, y, x + 1.6, y + 1.6), fill=_darken(color, .28))
    c.draw.rounded_rectangle(c.box(41, 23.5, 59, 26), radius=c.u(1), fill=_lighten(color, .35))
    c.highlight((32.5, 26, 35.5, 76), 2, 55)


def draw_round(c, color, variant):
    """Smartwatch, football, earbuds case."""
    if variant == 'watch':
        c.shadow(50, 86, 26, 4)
        c.shaded_rect((40, 6, 60, 94), _darken(color, .1), 5)
        c.shaded_rect((30, 30, 70, 70), (36, 38, 44), 10)
        c.shaded_rect((33, 33, 67, 67), (12, 12, 16), 8)
        cx, cy = c.u(50), c.u(50)
        for i, (r, col) in enumerate(((13, (255, 80, 110)), (10, (130, 230, 90)), (7, (90, 210, 255)))):
            rr = c.u(r)
            c.draw.arc((cx - rr, cy - rr, cx + rr, cy + rr), -90, -90 + 260 - i * 50, fill=col, width=c.u(2))
        c.draw.rounded_rectangle(c.box(70, 44, 72.5, 52), radius=c.u(1), fill=(150, 150, 156))
        return
    if variant == 'ball':
        c.shadow(50, 76, 42, 6)
        c.shaded_ellipse((28, 30, 72, 74), (246, 246, 244))
        cx, cy, r = 50, 52, 7
        pts = [(cx + r * math.cos(math.radians(a - 90)), cy + r * math.sin(math.radians(a - 90)))
               for a in range(0, 360, 72)]
        c.draw.polygon([(c.u(x), c.u(y)) for x, y in pts], fill=(30, 30, 34))
        for x, y in pts:
            dx, dy = x - cx, y - cy
            c.draw.line((c.u(x), c.u(y), c.u(cx + dx * 2.4), c.u(cy + dy * 2.4)), fill=(60, 60, 64), width=c.u(.6))
        c.highlight((35, 30, 44, 38), 4, 70)
        return
    # earbuds case
    c.shadow(50, 74, 46, 6)
    c.shaded_rect((27, 34, 73, 74), (248, 248, 250), 16)
    c.draw.line(c.box(27.5, 47, 72.5, 47), fill=(212, 212, 218), width=c.u(.5))
    c.draw.ellipse(c.box(48.5, 56, 51.5, 59), fill=color)
    c.highlight((30, 38, 34, 68), 6, 60)


def draw_laptop(c, color, variant):
    c.shadow(50, 80, 74, 6)
    c.shaded_rect((22, 22, 78, 70), _darken(color, .3), 3)
    c.shaded_rect((24.5, 24.5, 75.5, 67.5), (20, 22, 30), 1.5, vertical=True)
    c.shaded_rect((26, 26, 74, 66), _lighten(color, .25), 1, vertical=True)
    c.draw.rounded_rectangle(c.box(30, 32, 52, 36), radius=c.u(1), fill=_lighten(color, .7))
    c.draw.rounded_rectangle(c.box(30, 40, 66, 58), radius=c.u(1.5), fill=_lighten(color, .5))
    c.shaded_rect((12, 70, 88, 76), _lighten(color, .4), 2, vertical=True)
    c.draw.rounded_rectangle(c.box(42, 70, 58, 72), radius=c.u(1), fill=_darken(color, .2))


def draw_bag(c, color, variant):
    backpack = variant == 'backpack'
    c.shadow(50, 84, 54, 6)
    if backpack:
        c.draw.rounded_rectangle(c.box(38, 12, 62, 30), radius=c.u(8), outline=_darken(color, .3), width=c.u(2.4))
        c.shaded_rect((26, 22, 74, 84), color, 12)
        c.shaded_rect((32, 54, 68, 78), _darken(color, .12), 6)
        c.draw.line(c.box(34, 60, 66, 60), fill=_darken(color, .35), width=c.u(.8))
        c.highlight((29, 28, 32, 76), 2, 45)
        return
    c.draw.arc(c.box(35, 16, 65, 52), 180, 360, fill=_darken(color, .3), width=c.u(2.6))
    c.draw.polygon([(c.u(24), c.u(84)), (c.u(76), c.u(84)), (c.u(70), c.u(36)), (c.u(30), c.u(36))],
                   fill=color)
    c.shaded_rect((30, 36, 70, 44), _darken(color, .1), 1.5)
    c.draw.rounded_rectangle(c.box(46, 44, 54, 49), radius=c.u(1), fill=(205, 175, 105))
    c.highlight((31, 46, 33.5, 80), 1, 40)


def draw_lamp(c, color, variant):
    c.shadow(50, 86, 34, 5)
    c.shaded_rect((36, 80, 64, 86), _darken(color, .3), 3, vertical=True)
    c.shaded_rect((48.6, 44, 51.4, 81), (190, 170, 120), 1)
    c.draw.polygon([(c.u(30), c.u(46)), (c.u(70), c.u(46)), (c.u(61), c.u(14)), (c.u(39), c.u(14))], fill=color)
    c.draw.polygon([(c.u(32), c.u(46)), (c.u(37), c.u(46)), (c.u(42), c.u(14)), (c.u(39), c.u(14))],
                   fill=_lighten(color, .3))
    c.draw.ellipse(c.box(42, 43, 58, 49), fill=(255, 236, 170))


def draw_box(c, color, variant):
    """Air fryer, kettle, blender, iron — a rounded appliance body with a control."""
    if variant == 'kettle':
        c.shadow(48, 82, 50, 6)
        c.draw.rounded_rectangle(c.box(62, 30, 80, 66), radius=c.u(8), outline=_darken(color, .4), width=c.u(3.6))
        c.draw.polygon([(c.u(26), c.u(36)), (c.u(14), c.u(30)), (c.u(17), c.u(27)), (c.u(30), c.u(32))],
                       fill=_darken(color, .05))
        c.shaded_rect((26, 28, 66, 78), color, 12)
        c.shaded_rect((24, 76, 68, 84), (40, 40, 46), 2.5, vertical=True)
        c.shaded_rect((40, 21, 52, 29), (40, 40, 46), 2)
        c.highlight((29, 34, 32.5, 72), 2, 60)
        return
    if variant == 'blender':
        c.shadow(50, 86, 38, 5)
        c.shaded_rect((34, 62, 66, 86), (44, 44, 50), 5)
        c.draw.ellipse(c.box(47, 70, 53, 76), fill=color)
        c.shaded_rect((36, 16, 64, 62), _lighten(color, .55), 4)
        c.shaded_rect((38, 34, 62, 60), color, 3)
        c.shaded_rect((34, 12, 66, 18), (44, 44, 50), 2)
        c.highlight((38.5, 19, 41, 58), 2, 70)
        return
    c.shadow(50, 84, 56, 6)
    c.shaded_rect((24, 22, 76, 84), color, 10)
    c.shaded_rect((30, 52, 70, 80), _darken(color, .18), 6)
    c.draw.rounded_rectangle(c.box(44, 58, 56, 61), radius=c.u(1), fill=_lighten(color, .5))
    c.shaded_rect((36, 28, 64, 42), (24, 26, 32), 3)
    for i in range(3):
        c.draw.ellipse(c.box(40 + i * 8, 33, 44 + i * 8, 37), fill=(255, 150, 80) if i == 0 else (90, 94, 104))
    c.highlight((27, 26, 30.5, 76), 2, 50)


def draw_dumbbell(c, color, variant):
    if variant == 'mat':
        c.shadow(50, 78, 64, 6)
        c.shaded_rect((18, 46, 82, 78), color, 16)
        c.draw.ellipse(c.box(62, 46, 82, 78), fill=_darken(color, .2))
        c.draw.ellipse(c.box(66, 52, 78, 72), fill=_darken(color, .35))
        c.draw.line(c.box(30, 44, 30, 80), fill=(40, 40, 46), width=c.u(1.4))
        c.draw.line(c.box(56, 44, 56, 80), fill=(40, 40, 46), width=c.u(1.4))
        return
    c.shadow(50, 74, 70, 6)
    c.shaded_rect((30, 50, 70, 56), (170, 172, 178), 1.5, vertical=True)
    for x0 in (16, 70):
        c.shaded_rect((x0, 34, x0 + 14, 72), color, 4)
        c.shaded_rect((x0 + (14 if x0 < 50 else -5), 40, x0 + (19 if x0 < 50 else 0), 66), _darken(color, .2), 2)
    c.highlight((18, 37, 21, 68), 1.5, 50)


DRAWERS = {
    'phone': draw_phone, 'slab': draw_slab, 'bottle': draw_bottle, 'jar': draw_jar, 'cylinder': draw_cylinder,
    'round': draw_round, 'laptop': draw_laptop, 'bag': draw_bag, 'lamp': draw_lamp, 'box': draw_box,
    'dumbbell': draw_dumbbell,
}


def render_product(shape, color, background, variant='', seed=0, angle=0):
    canvas = Canvas(background, seed)
    DRAWERS[shape](canvas, _hex(color), variant)
    if angle:
        canvas.img = canvas.img.rotate(angle, resample=Image.BICUBIC, fillcolor=_hex(background))
    return canvas.finish()


def render_category(color, background, shape, variant=''):
    canvas = Canvas(background, 1)
    DRAWERS[shape](canvas, _hex(color), variant)
    return canvas.finish()
