bl_info = {
    "name": "Blokus Builder (Reverse Groove)",
    "author": "Blokus Builder Project",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Blokus",
    "description": "Generate Blokus-compatible board and pieces with reverse-groove mechanism",
    "category": "Object",
}

import bpy
import bmesh
import math
import os
from bpy.props import (
    FloatProperty, IntProperty, StringProperty,
    BoolProperty, EnumProperty, PointerProperty,
)
from bpy.types import PropertyGroup, Panel, Operator
from collections import defaultdict, deque

# ---------------------------------------------------------------------------
# 4. Piece Definitions (21 standard Blokus shapes)
# ---------------------------------------------------------------------------

PIECES = {
    # 1-cell (monomino)
    "I1": [(0, 0)],
    # 2-cell (domino)
    "I2": [(0, 0), (1, 0)],
    # 3-cell (trominoes)
    "I3": [(0, 0), (1, 0), (2, 0)],
    "L3": [(0, 0), (1, 0), (1, 1)],
    # 4-cell (tetrominoes)
    "I4": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "L4": [(0, 0), (1, 0), (2, 0), (2, 1)],
    "T4": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "O4": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "S4": [(0, 0), (1, 0), (1, 1), (2, 1)],
    # 5-cell (pentominoes)
    "F5": [(1, 0), (2, 0), (0, 1), (1, 1), (1, 2)],
    "I5": [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)],
    "L5": [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1)],
    "N5": [(0, 0), (1, 0), (1, 1), (2, 1), (3, 1)],
    "P5": [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2)],
    "T5": [(0, 0), (1, 0), (2, 0), (1, 1), (1, 2)],
    "U5": [(0, 0), (2, 0), (0, 1), (1, 1), (2, 1)],
    "V5": [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)],
    "W5": [(0, 0), (0, 1), (1, 1), (1, 2), (2, 2)],
    "X5": [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)],
    "Y5": [(0, 0), (1, 0), (2, 0), (3, 0), (1, 1)],
    "Z5": [(0, 0), (1, 0), (1, 1), (1, 2), (2, 2)],
}

COLORS = ["RED", "BLUE", "YELLOW", "GREEN"]

# ---------------------------------------------------------------------------
# 4.2 Validation
# ---------------------------------------------------------------------------

def validate_pieces():
    """Check piece data invariants. Returns (ok, messages)."""
    msgs = []
    total_cells = 0
    size_counts = defaultdict(int)

    for name, cells in PIECES.items():
        n = len(cells)
        total_cells += n
        size_counts[n] += 1

        # uniqueness
        if len(set(cells)) != n:
            msgs.append(f"{name}: duplicate cells")

        # connectivity (BFS)
        cell_set = set(cells)
        visited = set()
        queue = deque([cells[0]])
        visited.add(cells[0])
        while queue:
            cx, cy = queue.popleft()
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nb = (cx + dx, cy + dy)
                if nb in cell_set and nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        if visited != cell_set:
            msgs.append(f"{name}: not connected")

    if total_cells != 89:
        msgs.append(f"Total cells = {total_cells}, expected 89")

    expected = {1: 1, 2: 1, 3: 2, 4: 5, 5: 12}
    for sz, cnt in expected.items():
        if size_counts.get(sz, 0) != cnt:
            msgs.append(f"Size-{sz} count = {size_counts.get(sz, 0)}, expected {cnt}")

    return (len(msgs) == 0, msgs)


def validate_params(p):
    """Check parameter sanity. Returns (ok, messages)."""
    msgs = []
    groove_w = p.rib_w + 2 * p.clear
    groove_d = p.rib_h + 0.25
    remaining = p.piece_t - groove_d
    if remaining < 1.6:
        msgs.append(f"Remaining wall = {remaining:.2f}mm (min 1.6mm). "
                     f"Increase piece_t or reduce rib_h.")
    if p.clear < 0:
        msgs.append("Clearance must be >= 0")
    if p.clear > 0.35:
        msgs.append(f"Clearance {p.clear:.2f}mm is large; pieces may rattle")
    if groove_w <= p.rib_w:
        msgs.append("groove_w must be > rib_w (check clearance)")
    return (len(msgs) == 0, msgs)

# ---------------------------------------------------------------------------
# 3. Property Group
# ---------------------------------------------------------------------------

class BLK_Properties(PropertyGroup):
    # Cell
    cell: FloatProperty(name="Cell Size", default=20.0, min=5.0, max=50.0,
                        description="Cell size in mm", unit='LENGTH')
    clear: FloatProperty(name="Clearance", default=0.20, min=0.0, max=1.0,
                         description="One-side clearance in mm", unit='LENGTH')
    # Board
    board_t: FloatProperty(name="Board Thickness", default=1.8, min=0.5, max=5.0,
                           description="Base plate thickness", unit='LENGTH')
    rib_w: FloatProperty(name="Rib Width", default=1.2, min=0.4, max=5.0,
                         description="Grid rib width", unit='LENGTH')
    rib_h: FloatProperty(name="Rib Height", default=0.9, min=0.2, max=3.0,
                         description="Grid rib height", unit='LENGTH')
    frame_w: FloatProperty(name="Frame Width", default=8.0, min=0.0, max=20.0,
                           description="Outer frame width", unit='LENGTH')
    # Piece
    piece_t: FloatProperty(name="Piece Thickness", default=3.2, min=1.5, max=10.0,
                           description="Piece thickness", unit='LENGTH')
    bevel_top: FloatProperty(name="Bevel Top", default=0.4, min=0.0, max=2.0,
                             description="Top edge bevel", unit='LENGTH')
    bevel_bottom: FloatProperty(name="Bevel Bottom", default=0.2, min=0.0, max=2.0,
                                description="Bottom edge bevel (elephant foot)", unit='LENGTH')
    # Split
    split_x: IntProperty(name="Split X", default=2, min=1, max=10)
    split_y: IntProperty(name="Split Y", default=2, min=1, max=10)
    dowel_d: FloatProperty(name="Dowel Diameter", default=6.0, min=1.0, max=20.0,
                           unit='LENGTH')
    dowel_len: FloatProperty(name="Dowel Length", default=4.0, min=1.0, max=20.0,
                             unit='LENGTH')
    dowel_clear: FloatProperty(name="Dowel Clearance", default=0.2, min=0.0, max=1.0,
                               unit='LENGTH')
    # Export
    export_dir: StringProperty(name="Export Dir", default="//exports",
                               subtype='DIR_PATH')
    export_mode: EnumProperty(
        name="Export Mode",
        items=[
            ('PER_PIECE', "Per Piece", "One STL per piece"),
            ('PER_COLOR', "Per Color", "One STL per color (joined)"),
            ('BOARD_TILES', "Board Tiles", "One STL per board tile"),
        ],
        default='PER_PIECE',
    )
    apply_transforms: BoolProperty(name="Apply Transforms", default=True)
    # Colors
    color_red: BoolProperty(name="Red", default=True)
    color_blue: BoolProperty(name="Blue", default=True)
    color_yellow: BoolProperty(name="Yellow", default=True)
    color_green: BoolProperty(name="Green", default=True)
    # Generate All options
    make_board: BoolProperty(name="Board", default=True)
    make_pieces: BoolProperty(name="Pieces", default=True)
    # Debug
    keep_cutters: BoolProperty(name="Keep Cutters", default=False,
                               description="Keep Boolean cutter objects for debugging")
    # Layout
    layout_gap: FloatProperty(name="Layout Gap", default=2.0, min=0.0, max=20.0,
                              description="Gap between pieces on plate", unit='LENGTH')

# ---------------------------------------------------------------------------
# 5.1 Utility functions
# ---------------------------------------------------------------------------

def ensure_scene_units_mm():
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001  # 1 BU = 1 mm


def get_or_create_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def wipe_collection(name):
    if name not in bpy.data.collections:
        return
    col = bpy.data.collections[name]
    for obj in list(col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(col)


def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def link_to_collection(obj, col_name):
    col = get_or_create_collection(col_name)
    if obj.name not in col.objects:
        col.objects.link(obj)
    # unlink from scene collection if present
    sc = bpy.context.scene.collection
    if obj.name in sc.objects:
        sc.objects.unlink(obj)


def enabled_colors(p):
    cols = []
    if p.color_red:
        cols.append("RED")
    if p.color_blue:
        cols.append("BLUE")
    if p.color_yellow:
        cols.append("YELLOW")
    if p.color_green:
        cols.append("GREEN")
    return cols

# ---------------------------------------------------------------------------
# 5.3.1 Piece outline: cells -> contour -> extruded mesh
# ---------------------------------------------------------------------------

def cells_to_outline(cells):
    """Return ordered list of (x, y) vertices forming the outer contour."""
    edge_count = defaultdict(int)
    for (cx, cy) in cells:
        # 4 edges of unit square at (cx, cy)
        edges = [
            ((cx, cy), (cx + 1, cy)),       # bottom
            ((cx + 1, cy), (cx + 1, cy + 1)),  # right
            ((cx, cy + 1), (cx + 1, cy + 1)),  # top
            ((cx, cy), (cx, cy + 1)),        # left
        ]
        for e in edges:
            key = tuple(sorted(e))
            edge_count[key] += 1

    # Keep only boundary edges (count == 1)
    boundary = [e for e, c in edge_count.items() if c == 1]

    # Build adjacency
    adj = defaultdict(list)
    for a, b in boundary:
        adj[a].append(b)
        adj[b].append(a)

    # Walk the loop
    if not boundary:
        return []
    start = boundary[0][0]
    loop = [start]
    visited_edges = set()
    current = start
    while True:
        found_next = False
        for nb in adj[current]:
            edge_key = tuple(sorted((current, nb)))
            if edge_key not in visited_edges:
                visited_edges.add(edge_key)
                loop.append(nb)
                current = nb
                found_next = True
                break
        if not found_next:
            break

    # Remove last if it equals first (closed loop)
    if len(loop) > 1 and loop[-1] == loop[0]:
        loop.pop()

    return loop


def create_piece_mesh(name, cells, cell_size, piece_t, bevel_top):
    """Create an extruded piece mesh from cell coordinates."""
    outline = cells_to_outline(cells)
    if not outline:
        return None

    bm = bmesh.new()

    # Create bottom face vertices
    bottom_verts = []
    top_verts = []
    for (gx, gy) in outline:
        x = gx * cell_size
        y = gy * cell_size
        bv = bm.verts.new((x, y, 0.0))
        tv = bm.verts.new((x, y, piece_t))
        bottom_verts.append(bv)
        top_verts.append(tv)

    bm.verts.ensure_lookup_table()

    n = len(outline)

    # Bottom face (reversed winding for outward normal pointing down)
    try:
        bf = bm.faces.new(list(reversed(bottom_verts)))
    except Exception:
        bf = None

    # Top face
    try:
        tf = bm.faces.new(top_verts)
    except Exception:
        tf = None

    # Side faces
    for i in range(n):
        j = (i + 1) % n
        try:
            bm.faces.new([bottom_verts[i], bottom_verts[j],
                          top_verts[j], top_verts[i]])
        except Exception:
            pass

    bm.normal_update()

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    # Bevel top edges
    if bevel_top > 0:
        mod = obj.modifiers.new("BevelTop", 'BEVEL')
        mod.width = bevel_top
        mod.segments = 2
        mod.limit_method = 'ANGLE'
        mod.angle_limit = math.radians(60)
        select_only(obj)
        bpy.ops.object.modifier_apply(modifier=mod.name)

    return obj

# ---------------------------------------------------------------------------
# 5.3.2-3 Groove generation (Boolean)
# ---------------------------------------------------------------------------

def get_grid_lines_for_piece(cells):
    """Return lists of X and Y grid-line indices that the piece spans (including outer edges)."""
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    # Grid lines at every integer boundary from min to max+1
    x_lines = list(range(min_x, max_x + 2))  # includes outer boundaries
    y_lines = list(range(min_y, max_y + 2))
    return x_lines, y_lines


def make_groove_cutter(name, cells, cell_size, groove_w, groove_d, piece_t):
    """Create a single joined object of groove bars for Boolean subtraction."""
    x_lines, y_lines = get_grid_lines_for_piece(cells)
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    piece_x_min = min_x * cell_size
    piece_x_max = (max_x + 1) * cell_size
    piece_y_min = min_y * cell_size
    piece_y_max = (max_y + 1) * cell_size

    bars = []

    # X-direction grid lines (vertical lines -> bars along Y)
    for gx in x_lines:
        x_center = gx * cell_size
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(
                x_center,
                (piece_y_min + piece_y_max) / 2,
                groove_d / 2,
            ),
            scale=(
                groove_w,
                piece_y_max - piece_y_min + groove_w * 2,  # extend a bit
                groove_d,
            ),
        )
        bar = bpy.context.active_object
        bar.name = f"_bar_x_{gx}"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bars.append(bar)

    # Y-direction grid lines (horizontal lines -> bars along X)
    for gy in y_lines:
        y_center = gy * cell_size
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(
                (piece_x_min + piece_x_max) / 2,
                y_center,
                groove_d / 2,
            ),
            scale=(
                piece_x_max - piece_x_min + groove_w * 2,
                groove_w,
                groove_d,
            ),
        )
        bar = bpy.context.active_object
        bar.name = f"_bar_y_{gy}"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bars.append(bar)

    if not bars:
        return None

    # Join all bars into one object
    bpy.ops.object.select_all(action='DESELECT')
    for b in bars:
        b.select_set(True)
    bpy.context.view_layer.objects.active = bars[0]
    bpy.ops.object.join()
    cutter = bpy.context.active_object
    cutter.name = name
    return cutter


def apply_boolean(target, cutter, operation='DIFFERENCE'):
    """Apply a Boolean modifier. Returns True on success."""
    select_only(target)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    select_only(cutter)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    select_only(target)
    mod = target.modifiers.new("Bool", 'BOOLEAN')
    mod.operation = operation
    mod.object = cutter
    mod.solver = 'EXACT'
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        return True
    except Exception:
        # Retry with FAST solver
        target.modifiers.remove(mod)
        mod2 = target.modifiers.new("Bool2", 'BOOLEAN')
        mod2.operation = operation
        mod2.object = cutter
        mod2.solver = 'FAST'
        try:
            bpy.ops.object.modifier_apply(modifier=mod2.name)
            return True
        except Exception:
            if mod2.name in [m.name for m in target.modifiers]:
                target.modifiers.remove(mod2)
            return False


def create_piece_with_grooves(piece_name, cells, color, p):
    """Full pipeline: outline + grooves -> final piece object."""
    cell = p.cell
    piece_t = p.piece_t
    groove_w = p.rib_w + 2 * p.clear
    groove_d = p.rib_h + 0.25

    obj_name = f"BLK_P_{color}_{piece_name}"
    col_name = f"BLK_PIECES_{color}"

    # 1) Create extruded piece
    piece_obj = create_piece_mesh(obj_name, cells, cell, piece_t, p.bevel_top)
    if piece_obj is None:
        return None

    # 2) Create groove cutter
    cutter_name = f"_BLK_CUT_{color}_{piece_name}"
    cutter = make_groove_cutter(cutter_name, cells, cell, groove_w, groove_d, piece_t)

    if cutter is not None:
        # 3) Trim cutter to piece footprint via INTERSECT
        # Make a copy of the piece for intersection (we need the original intact)
        select_only(piece_obj)
        bpy.ops.object.duplicate(linked=False)
        piece_copy = bpy.context.active_object
        piece_copy.name = f"_trim_{obj_name}"

        ok = apply_boolean(cutter, piece_copy, 'INTERSECT')
        # Remove the copy
        bpy.data.objects.remove(piece_copy, do_unlink=True)

        if ok:
            # 4) Subtract trimmed cutter from piece
            apply_boolean(piece_obj, cutter, 'DIFFERENCE')

        # Cleanup cutter
        if not p.keep_cutters:
            if cutter and cutter.name in bpy.data.objects:
                bpy.data.objects.remove(cutter, do_unlink=True)
        else:
            link_to_collection(cutter, "BLK_TMP")

    # Recalculate normals
    select_only(piece_obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    # Store params as custom properties
    piece_obj["blk_cell"] = cell
    piece_obj["blk_clear"] = p.clear
    piece_obj["blk_piece_name"] = piece_name
    piece_obj["blk_color"] = color

    # Move to collection
    link_to_collection(piece_obj, col_name)

    return piece_obj

# ---------------------------------------------------------------------------
# 5.2 Board generation
# ---------------------------------------------------------------------------

def create_board_tile(tile_x, tile_y, p):
    """Generate one board tile with base plate, grid ribs, and frame portion."""
    cell = p.cell
    grid = 20
    cells_per_tile_x = grid // p.split_x
    cells_per_tile_y = grid // p.split_y

    # Cell range for this tile
    cx_start = tile_x * cells_per_tile_x
    cx_end = cx_start + cells_per_tile_x
    cy_start = tile_y * cells_per_tile_y
    cy_end = cy_start + cells_per_tile_y

    # Frame extends only on outer edges
    frame_left = p.frame_w if tile_x == 0 else 0
    frame_right = p.frame_w if tile_x == p.split_x - 1 else 0
    frame_bottom = p.frame_w if tile_y == 0 else 0
    frame_top = p.frame_w if tile_y == p.split_y - 1 else 0

    # Tile physical bounds
    x_min = cx_start * cell - frame_left
    x_max = cx_end * cell + frame_right
    y_min = cy_start * cell - frame_bottom
    y_max = cy_end * cell + frame_top
    tile_w = x_max - x_min
    tile_h = y_max - y_min

    objs = []

    # Base plate
    bpy.ops.mesh.primitive_cube_add(
        size=1,
        location=(
            (x_min + x_max) / 2,
            (y_min + y_max) / 2,
            -p.board_t / 2,
        ),
        scale=(tile_w, tile_h, p.board_t),
    )
    base = bpy.context.active_object
    base.name = f"_base_{tile_x}_{tile_y}"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    objs.append(base)

    # Grid ribs (vertical: along X grid lines within this tile)
    # X grid lines: from cx_start to cx_end (inclusive = cells_per_tile_x + 1 lines)
    for gx in range(cx_start, cx_end + 1):
        x_pos = gx * cell
        # Rib spans the cell region (not the frame region)
        rib_y_min = cy_start * cell
        rib_y_max = cy_end * cell
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(
                x_pos,
                (rib_y_min + rib_y_max) / 2,
                p.rib_h / 2,
            ),
            scale=(p.rib_w, rib_y_max - rib_y_min, p.rib_h),
        )
        rib = bpy.context.active_object
        rib.name = f"_ribX_{gx}"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(rib)

    # Y grid lines (horizontal)
    for gy in range(cy_start, cy_end + 1):
        y_pos = gy * cell
        rib_x_min = cx_start * cell
        rib_x_max = cx_end * cell
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(
                (rib_x_min + rib_x_max) / 2,
                y_pos,
                p.rib_h / 2,
            ),
            scale=(rib_x_max - rib_x_min, p.rib_w, p.rib_h),
        )
        rib = bpy.context.active_object
        rib.name = f"_ribY_{gy}"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(rib)

    # Frame walls (raised edges on outer borders of the full board)
    frame_h = p.rib_h + 1.5  # frame taller than ribs

    if frame_left > 0:
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(x_min + frame_left / 2, (y_min + y_max) / 2, frame_h / 2),
            scale=(frame_left, tile_h, frame_h),
        )
        fw = bpy.context.active_object
        fw.name = "_frame_left"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(fw)

    if frame_right > 0:
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(x_max - frame_right / 2, (y_min + y_max) / 2, frame_h / 2),
            scale=(frame_right, tile_h, frame_h),
        )
        fw = bpy.context.active_object
        fw.name = "_frame_right"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(fw)

    if frame_bottom > 0:
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=((x_min + x_max) / 2, y_min + frame_bottom / 2, frame_h / 2),
            scale=(tile_w, frame_bottom, frame_h),
        )
        fw = bpy.context.active_object
        fw.name = "_frame_bottom"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(fw)

    if frame_top > 0:
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=((x_min + x_max) / 2, y_max - frame_top / 2, frame_h / 2),
            scale=(tile_w, frame_top, frame_h),
        )
        fw = bpy.context.active_object
        fw.name = "_frame_top"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(fw)

    # Anti-warp reinforcement ribs on underside
    reinforce_count = 3
    reinforce_h = 1.2
    reinforce_w = 1.0
    cell_x_min = cx_start * cell
    cell_x_max = cx_end * cell
    cell_y_min = cy_start * cell
    cell_y_max = cy_end * cell
    span_x = cell_x_max - cell_x_min
    span_y = cell_y_max - cell_y_min

    for i in range(reinforce_count):
        frac = (i + 1) / (reinforce_count + 1)
        # Horizontal reinforcement
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(
                (cell_x_min + cell_x_max) / 2,
                cell_y_min + span_y * frac,
                -p.board_t - reinforce_h / 2,
            ),
            scale=(span_x * 0.95, reinforce_w, reinforce_h),
        )
        rr = bpy.context.active_object
        rr.name = f"_reinforce_h_{i}"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(rr)

        # Vertical reinforcement
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(
                cell_x_min + span_x * frac,
                (cell_y_min + cell_y_max) / 2,
                -p.board_t - reinforce_h / 2,
            ),
            scale=(reinforce_w, span_y * 0.95, reinforce_h),
        )
        rr = bpy.context.active_object
        rr.name = f"_reinforce_v_{i}"
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(rr)

    # Dowel posts / holes at tile boundaries
    # Add dowel posts on right/top edges, holes on left/bottom edges
    dowel_r = p.dowel_d / 2
    dowel_r_hole = dowel_r + p.dowel_clear
    half_len = p.dowel_len / 2

    def add_cylinder(cx, cy, cz, radius, depth, cyl_name):
        bpy.ops.mesh.primitive_cylinder_add(
            radius=radius,
            depth=depth,
            location=(cx, cy, cz),
            vertices=24,
        )
        c = bpy.context.active_object
        c.name = cyl_name
        return c

    # Right edge dowels (posts on right tile, holes on left tile)
    if tile_x < p.split_x - 1:
        edge_x = cx_end * cell
        mid_y = (cy_start + cy_end) * cell / 2
        spacing = (cy_end - cy_start) * cell / 3
        for di, offset in enumerate([-spacing / 2, spacing / 2]):
            post = add_cylinder(
                edge_x, mid_y + offset,
                -p.board_t - half_len,
                dowel_r, p.dowel_len,
                f"_dowel_post_r_{tile_x}_{tile_y}_{di}",
            )
            objs.append(post)

    if tile_x > 0:
        edge_x = cx_start * cell
        mid_y = (cy_start + cy_end) * cell / 2
        spacing = (cy_end - cy_start) * cell / 3
        for di, offset in enumerate([-spacing / 2, spacing / 2]):
            hole = add_cylinder(
                edge_x, mid_y + offset,
                -p.board_t - half_len,
                dowel_r_hole, p.dowel_len + 0.5,
                f"_dowel_hole_l_{tile_x}_{tile_y}_{di}",
            )
            # Boolean subtract hole from base
            # We need to do this after joining, so mark it
            hole["_is_hole"] = True
            objs.append(hole)

    # Top edge dowels
    if tile_y < p.split_y - 1:
        edge_y = cy_end * cell
        mid_x = (cx_start + cx_end) * cell / 2
        spacing = (cx_end - cx_start) * cell / 3
        for di, offset in enumerate([-spacing / 2, spacing / 2]):
            post = add_cylinder(
                mid_x + offset, edge_y,
                -p.board_t - half_len,
                dowel_r, p.dowel_len,
                f"_dowel_post_t_{tile_x}_{tile_y}_{di}",
            )
            objs.append(post)

    if tile_y > 0:
        edge_y = cy_start * cell
        mid_x = (cx_start + cx_end) * cell / 2
        spacing = (cx_end - cx_start) * cell / 3
        for di, offset in enumerate([-spacing / 2, spacing / 2]):
            hole = add_cylinder(
                mid_x + offset, edge_y,
                -p.board_t - half_len,
                dowel_r_hole, p.dowel_len + 0.5,
                f"_dowel_hole_b_{tile_x}_{tile_y}_{di}",
            )
            hole["_is_hole"] = True
            objs.append(hole)

    # Separate holes from non-holes
    holes = [o for o in objs if o.get("_is_hole")]
    solids = [o for o in objs if not o.get("_is_hole")]

    # Join solids
    bpy.ops.object.select_all(action='DESELECT')
    for o in solids:
        o.select_set(True)
    bpy.context.view_layer.objects.active = solids[0]
    bpy.ops.object.join()
    tile_obj = bpy.context.active_object
    tile_obj.name = f"BLK_B_{tile_x}_{tile_y}"

    # Subtract holes
    for hole in holes:
        apply_boolean(tile_obj, hole, 'DIFFERENCE')
        if hole.name in bpy.data.objects:
            bpy.data.objects.remove(hole, do_unlink=True)

    # Store params
    tile_obj["blk_cell"] = cell
    tile_obj["blk_tile_x"] = tile_x
    tile_obj["blk_tile_y"] = tile_y

    link_to_collection(tile_obj, "BLK_BOARD")
    return tile_obj

# ---------------------------------------------------------------------------
# 6. Layout (shelf packing)
# ---------------------------------------------------------------------------

def layout_pieces_shelf(color, piece_objects, gap, cell):
    """Arrange piece objects in a shelf layout, sorted by bounding-box area descending."""
    if not piece_objects:
        return

    # Sort by bounding box area (descending)
    def bbox_area(obj):
        bb = obj.bound_box
        xs = [v[0] for v in bb]
        ys = [v[1] for v in bb]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))

    piece_objects.sort(key=bbox_area, reverse=True)

    # Shelf packing
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    max_row_width = cell * 25  # reasonable row width

    for obj in piece_objects:
        bb = obj.bound_box
        xs = [v[0] for v in bb]
        ys = [v[1] for v in bb]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        ox = min(xs)
        oy = min(ys)

        if cursor_x + w > max_row_width and cursor_x > 0:
            cursor_x = 0.0
            cursor_y += row_height + gap
            row_height = 0.0

        obj.location.x += (cursor_x - ox)
        obj.location.y += (cursor_y - oy)

        cursor_x += w + gap
        row_height = max(row_height, h)


# ---------------------------------------------------------------------------
# 7. STL Export
# ---------------------------------------------------------------------------

def export_stl_objects(objects, filepath, apply_transforms):
    """Export a list of objects to STL."""
    dirpath = os.path.dirname(filepath)
    os.makedirs(dirpath, exist_ok=True)

    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]

    if apply_transforms:
        for obj in objects:
            select_only(obj)
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        # Re-select all
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]

    bpy.ops.export_mesh.stl(filepath=filepath, use_selection=True)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class BLK_OT_GenerateBoard(Operator):
    bl_idname = "blk.generate_board"
    bl_label = "Generate Board"
    bl_description = "Generate the Blokus board (split tiles with ribs and dowels)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.blk_params
        ok, msgs = validate_params(p)
        if not ok:
            for m in msgs:
                self.report({'ERROR'}, m)
            return {'CANCELLED'}

        ensure_scene_units_mm()
        wipe_collection("BLK_BOARD")

        for tx in range(p.split_x):
            for ty in range(p.split_y):
                create_board_tile(tx, ty, p)

        self.report({'INFO'}, f"Board generated: {p.split_x}x{p.split_y} tiles")
        return {'FINISHED'}


class BLK_OT_GeneratePieces(Operator):
    bl_idname = "blk.generate_pieces"
    bl_label = "Generate Pieces"
    bl_description = "Generate all Blokus pieces with reverse grooves"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.blk_params
        ok_p, msgs_p = validate_pieces()
        if not ok_p:
            for m in msgs_p:
                self.report({'ERROR'}, m)
            return {'CANCELLED'}
        ok_v, msgs_v = validate_params(p)
        if not ok_v:
            for m in msgs_v:
                self.report({'ERROR'}, m)
            return {'CANCELLED'}

        ensure_scene_units_mm()

        colors = enabled_colors(p)
        for color in colors:
            col_name = f"BLK_PIECES_{color}"
            wipe_collection(col_name)

        wipe_collection("BLK_TMP")

        total = 0
        for ci, color in enumerate(colors):
            piece_objs = []
            for piece_name, cells in PIECES.items():
                obj = create_piece_with_grooves(piece_name, cells, color, p)
                if obj:
                    piece_objs.append(obj)
                    total += 1

            # Layout with Y offset per color
            color_offset_y = ci * (p.cell * 12 + p.layout_gap * 5)
            layout_pieces_shelf(color, piece_objs, p.layout_gap, p.cell)
            for obj in piece_objs:
                obj.location.y += color_offset_y

        if not p.keep_cutters:
            wipe_collection("BLK_TMP")

        self.report({'INFO'}, f"Generated {total} pieces")
        return {'FINISHED'}


class BLK_OT_GenerateAll(Operator):
    bl_idname = "blk.generate_all"
    bl_label = "Generate All"
    bl_description = "Generate board and pieces"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.blk_params
        if p.make_board:
            bpy.ops.blk.generate_board()
        if p.make_pieces:
            bpy.ops.blk.generate_pieces()
        return {'FINISHED'}


class BLK_OT_ExportSTL(Operator):
    bl_idname = "blk.export_stl"
    bl_label = "Export STL"
    bl_description = "Export generated objects to STL files"
    bl_options = {'REGISTER'}

    def execute(self, context):
        p = context.scene.blk_params
        base_dir = bpy.path.abspath(p.export_dir)
        if not base_dir:
            self.report({'ERROR'}, "Export directory not set")
            return {'CANCELLED'}

        exported = 0

        if p.export_mode == 'BOARD_TILES':
            col_name = "BLK_BOARD"
            if col_name in bpy.data.collections:
                board_dir = os.path.join(base_dir, "board")
                for obj in bpy.data.collections[col_name].objects:
                    fpath = os.path.join(board_dir, f"{obj.name}.stl")
                    export_stl_objects([obj], fpath, p.apply_transforms)
                    exported += 1

        elif p.export_mode == 'PER_PIECE':
            for color in enabled_colors(p):
                col_name = f"BLK_PIECES_{color}"
                if col_name in bpy.data.collections:
                    piece_dir = os.path.join(base_dir, "pieces", color.lower())
                    for obj in bpy.data.collections[col_name].objects:
                        fpath = os.path.join(piece_dir, f"{obj.name}.stl")
                        export_stl_objects([obj], fpath, p.apply_transforms)
                        exported += 1

        elif p.export_mode == 'PER_COLOR':
            for color in enabled_colors(p):
                col_name = f"BLK_PIECES_{color}"
                if col_name in bpy.data.collections:
                    objs = list(bpy.data.collections[col_name].objects)
                    if objs:
                        piece_dir = os.path.join(base_dir, "pieces")
                        fpath = os.path.join(piece_dir, f"{color.lower()}.stl")
                        export_stl_objects(objs, fpath, p.apply_transforms)
                        exported += 1

        # Also export board tiles if not in board-only mode
        if p.export_mode in ('PER_PIECE', 'PER_COLOR'):
            col_name = "BLK_BOARD"
            if col_name in bpy.data.collections:
                board_dir = os.path.join(base_dir, "board")
                for obj in bpy.data.collections[col_name].objects:
                    fpath = os.path.join(board_dir, f"{obj.name}.stl")
                    export_stl_objects([obj], fpath, p.apply_transforms)
                    exported += 1

        self.report({'INFO'}, f"Exported {exported} STL files to {base_dir}")
        return {'FINISHED'}


class BLK_OT_Clean(Operator):
    bl_idname = "blk.clean"
    bl_label = "Clean All"
    bl_description = "Remove all generated Blokus objects and collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        wipe_collection("BLK_BOARD")
        for color in COLORS:
            wipe_collection(f"BLK_PIECES_{color}")
        wipe_collection("BLK_TMP")
        self.report({'INFO'}, "Cleaned all Blokus objects")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI Panel
# ---------------------------------------------------------------------------

class BLK_PT_MainPanel(Panel):
    bl_label = "Blokus Builder"
    bl_idname = "BLK_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Blokus"

    def draw(self, context):
        layout = self.layout
        p = context.scene.blk_params

        # --- Dimensions ---
        box = layout.box()
        box.label(text="Cell & Clearance", icon='SNAP_GRID')
        box.prop(p, "cell")
        box.prop(p, "clear")

        # --- Board ---
        box = layout.box()
        box.label(text="Board", icon='MESH_GRID')
        box.prop(p, "board_t")
        box.prop(p, "rib_w")
        box.prop(p, "rib_h")
        box.prop(p, "frame_w")

        # --- Piece ---
        box = layout.box()
        box.label(text="Piece", icon='MESH_CUBE')
        box.prop(p, "piece_t")
        box.prop(p, "bevel_top")
        box.prop(p, "bevel_bottom")
        # Show computed groove values
        groove_w = p.rib_w + 2 * p.clear
        groove_d = p.rib_h + 0.25
        box.label(text=f"Groove W: {groove_w:.2f} mm")
        box.label(text=f"Groove D: {groove_d:.2f} mm")
        remaining = p.piece_t - groove_d
        if remaining < 1.6:
            box.label(text=f"WARNING: remaining wall {remaining:.2f} mm", icon='ERROR')

        # --- Split ---
        box = layout.box()
        box.label(text="Board Split", icon='MOD_ARRAY')
        row = box.row()
        row.prop(p, "split_x")
        row.prop(p, "split_y")
        box.prop(p, "dowel_d")
        box.prop(p, "dowel_len")
        box.prop(p, "dowel_clear")

        # --- Colors ---
        box = layout.box()
        box.label(text="Colors", icon='COLOR')
        row = box.row()
        row.prop(p, "color_red", toggle=True)
        row.prop(p, "color_blue", toggle=True)
        row = box.row()
        row.prop(p, "color_yellow", toggle=True)
        row.prop(p, "color_green", toggle=True)

        # --- Generate ---
        box = layout.box()
        box.label(text="Generate", icon='PLAY')
        row = box.row()
        row.prop(p, "make_board", toggle=True)
        row.prop(p, "make_pieces", toggle=True)
        box.prop(p, "layout_gap")
        box.operator("blk.generate_board", icon='MESH_GRID')
        box.operator("blk.generate_pieces", icon='MESH_CUBE')
        box.operator("blk.generate_all", icon='PLAY')

        # --- Export ---
        box = layout.box()
        box.label(text="Export", icon='EXPORT')
        box.prop(p, "export_dir")
        box.prop(p, "export_mode")
        box.prop(p, "apply_transforms")
        box.operator("blk.export_stl", icon='FILE_BLANK')

        # --- Cleanup ---
        box = layout.box()
        box.label(text="Utilities", icon='TOOL_SETTINGS')
        box.prop(p, "keep_cutters")
        box.operator("blk.clean", icon='TRASH')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    BLK_Properties,
    BLK_OT_GenerateBoard,
    BLK_OT_GeneratePieces,
    BLK_OT_GenerateAll,
    BLK_OT_ExportSTL,
    BLK_OT_Clean,
    BLK_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.blk_params = PointerProperty(type=BLK_Properties)


def unregister():
    del bpy.types.Scene.blk_params
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
