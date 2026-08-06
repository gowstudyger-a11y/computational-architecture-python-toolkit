import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino.Geometry as rg
import time
import pprint
import math

# BUILDING DATA STRUCTURE  

def initialize_building_data():
    """
    THIS IS THE MAIN DICTIONARY that will store ALL the building data.
    """
    Building = {
        "name": "Parametric Building",
        "location": "TH-OWL",
        
        # PLOT section
        "plot": {
            "length": 0.0,       
            "width": 0.0,      
            "boundary": None,   
        },
        
        # FLOORS section
        "floors": {
            "num_floors": 1,
            "floor_heights": [],
            "total_height": 0.0,
            "boundaries_per_floor": [],
            "boundary_coords_per_floor": [],  # Convex hull coordinates for each floor
        },
        
        # GRID section
        "grid": {
            "spacing": 0.0,
            "foundation_points": [],
            "selected_column_points": [],
            "selected_points_per_floor": [],
            "selected_coords_per_floor": [],
        },
        
        # STRUCTURE section
        "structure": {
            "columns": {
                "width": 0.0,
                "height": 0.0,
                "objects": [],
                "objects_per_floor": [],
                "top_points_per_floor": [],
            },
            
            "plinth_beams": {
                "width": 0.0,
                "depth": 0.0,
                "max_cantilever": 3.0,
                "extension_per_floor": [],
                "objects": [],
                "objects_per_floor": [],
                "intersection_points_per_floor": [],
            },
        },
        
        # GEOMETRY 
        "geometry": {
            "plot_boundary": None,
            "foundation_grid": [],
            "floor_grids": [],
            "floor_boundaries": [],
            "boundary_point_objects": [],
        }
    }
    
    return Building

# UTILITY FUNCTIONS        

def clear_plot():
    """Reset button - clear all layers"""
    
    layers_to_clear = [
        "Plot_Boundary",      
        "Foundation_Grid",    
        "Columns",           
        "Plinth_Grid",       
        "Plot_Grid",
        "Floor_Grid",
        "Floor_Boundary",
        "Boundary_Points",
        "Wooden_Beam"        
    ]
    
    for layer_name in layers_to_clear:
        if rs.IsLayer(layer_name):
            objs = rs.ObjectsByLayer(layer_name)
            if objs:
                rs.DeleteObjects(objs) 
            rs.DeleteLayer(layer_name)
    
    
def print_section_header(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_section_footer():
    print("=" * 60 + "\n")


def compute_convex_hull_2d(points_2d):
    """
    Compute convex hull using Graham scan algorithm.
    Input: list of (x, y) tuples
    Output: list of (x, y) tuples forming hull in counter-clockwise order
    """
    if len(points_2d) < 3:
        return list(points_2d)
    
    # Remove duplicates
    pts = list(set(points_2d))
    
    if len(pts) < 3:
        return pts
    
    # Find the bottom-most point (smallest y, then smallest x)
    start = min(pts, key=lambda p: (p[1], p[0]))
    
    # Sort points by polar angle with respect to start point
    def polar_angle(p):
        if p == start:
            return -float('inf')
        dx = p[0] - start[0]
        dy = p[1] - start[1]
        return math.atan2(dy, dx)
    
    def distance_sq(p):
        return (p[0] - start[0])**2 + (p[1] - start[1])**2
    
    # Sort by angle, then by distance for points with same angle
    sorted_pts = sorted(pts, key=lambda p: (polar_angle(p), distance_sq(p)))
    
    # Cross product: positive = left turn, negative = right turn, zero = collinear
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    
    # Build the hull using Graham scan
    hull = []
    for p in sorted_pts:
        # Remove points that make clockwise turns
        while len(hull) >= 2 and cross(hull[-2], hull[-1], p) <= 0:
            hull.pop()
        hull.append(p)
    
    return hull


def create_boundary_from_columns(Building, floor_num, column_top_points, z_level):
    """
    Create boundary by:
    1. Computing convex hull of column center points (finds OUTER columns only)
    2. Creating YELLOW POINTS only at boundary/hull column locations
    3. Creating YELLOW POLYLINE connecting those boundary points
    
    Returns: boundary polyline and hull coordinates
    """
    
    if not column_top_points or len(column_top_points) < 3:
        print("  Not enough columns for boundary (need at least 3)")
        # Still return something for 1-2 columns
        hull_coords = [(pt[0], pt[1], z_level) for pt in column_top_points]
        return None, hull_coords
    
    # Extract 2D points (x, y) from column tops
    points_2d = [(pt[0], pt[1]) for pt in column_top_points]
    
    # Compute convex hull - this returns ONLY the outer/perimeter columns
    hull_2d = compute_convex_hull_2d(points_2d)
    
    if len(hull_2d) < 3:
        print("  Convex hull has less than 3 points")
        hull_coords = [(pt[0], pt[1], z_level) for pt in hull_2d]
        return None, hull_coords
    
    # Create layer for boundary points (YELLOW)
    points_layer = "Boundary_Points"
    if not rs.IsLayer(points_layer):
        rs.AddLayer(points_layer, (255, 200, 0))  # Yellow
    
    # Create layer for boundary polyline (YELLOW)
    boundary_layer = "Floor_Boundary"
    if not rs.IsLayer(boundary_layer):
        rs.AddLayer(boundary_layer, (255, 200, 0))  # Yellow
    
    # Create 3D hull points at specified z level
    hull_3d = [(p[0], p[1], z_level) for p in hull_2d]
    
    # Create YELLOW POINTS only at boundary column locations (convex hull vertices)
    boundary_point_ids = []
    print("  Creating boundary points at {} outer columns...".format(len(hull_3d)))
    for pt in hull_3d:
        pt_id = rs.AddPoint(pt)
        if pt_id:
            rs.ObjectLayer(pt_id, points_layer)
            rs.ObjectColor(pt_id, (255, 200, 0))  # Yellow
            boundary_point_ids.append(pt_id)
    
    # Close the hull for polyline (connect last point back to first)
    hull_closed = hull_3d + [hull_3d[0]]
    
    # Create YELLOW boundary POLYLINE connecting boundary columns
    boundary = rs.AddPolyline(hull_closed)
    if boundary:
        rs.ObjectLayer(boundary, boundary_layer)
        rs.ObjectColor(boundary, (255, 200, 0))  # Yellow
    
    # Store in Building dictionary
    Building["floors"]["boundaries_per_floor"].append(boundary)
    Building["floors"]["boundary_coords_per_floor"].append(hull_3d)
    Building["geometry"]["floor_boundaries"].append(boundary)
    Building["geometry"]["boundary_point_objects"].extend(boundary_point_ids)
    
    print("  Floor {} boundary created:".format(floor_num))
    print("    - {} boundary points (convex hull vertices)".format(len(hull_2d)))
    print("    - Yellow polyline connecting outer columns")
    
    sc.doc.Views.Redraw()
    
    return boundary, hull_3d


# INPUT COLLECTION        
def get_plot_dimensions(Building):
    """Get plot length and width"""
    print_section_header("PARAMETRIC FOUNDATION TO PLINTH BEAM GRID GENERATOR")
    
    plot_length = rs.GetReal(
        "Enter PLOT LENGTH (meters)",
        number=60.0,
        minimum=10.0,
        maximum=200.0
    )
    
    if plot_length is None:
        print("Operation cancelled by user.")
        return False
    
    plot_width = rs.GetReal(
        "Enter PLOT WIDTH (meters)",
        number=20.0,
        minimum=5.0,
        maximum=100.0
    )
    
    if plot_width is None:
        print("Operation cancelled by user.")
        return False
    
    Building["plot"]["length"] = plot_length
    Building["plot"]["width"] = plot_width
    
    print_section_header("PLOT DIMENSIONS:")
    print("Plot: {} m x {} m".format(plot_length, plot_width))
    print_section_footer()
    
    return True

def get_grid_spacing(Building):
    """Get grid spacing for foundation"""
    print_section_header("NOW: Define foundation grid spacing")
    
    grid_size = rs.GetReal(
        "Enter FOUNDATION GRID SPACING - center to center (meters)",
        number=4.0,
        minimum=1.0,
        maximum=10.0
    )
    
    if grid_size is None:
        print("Operation cancelled by user.")
        return False
    
    Building["grid"]["spacing"] = grid_size
    
    print("Foundation Grid Spacing: {} m".format(grid_size))
    print_section_footer()
    
    return True  

def get_column_inputs(Building):
    """Get column WIDTH and HEIGHT for foundation floor"""
    print_section_header("NOW: Define column dimensions")
    
    column_width = rs.GetReal(
        "Enter COLUMN WIDTH (square column side, meters)",
        number=0.3,
        minimum=0.1,
        maximum=2.0
    )
    
    if column_width is None:
        print("Operation cancelled by user.")
        return False
    
    column_height = rs.GetReal(
        "Enter COLUMN HEIGHT for FOUNDATION FLOOR (meters)",
        number=3.0,
        minimum=0.5,
        maximum=10.0
    )
    
    if column_height is None:
        print("Operation cancelled by user.")
        return False
    
    Building["structure"]["columns"]["width"] = column_width
    Building["structure"]["columns"]["height"] = column_height
    Building["floors"]["floor_heights"].append(column_height)
    
    print("Column Width: {} m x {} m (square)".format(column_width, column_width))
    print("Foundation Column Height: {} m".format(column_height))
    print_section_footer()
    
    return True

def get_plinth_beam_width(Building):
    """Ask for plinth beam WIDTH only"""
    column_width = Building["structure"]["columns"]["width"]
    
    print_section_header("NOW: Define plinth beam width")
    print("NOTE: Plinth beam width must be <= Column width ({} m)".format(column_width))
    print_section_footer()
    
    beam_width = None
    while beam_width is None:
        input_width = rs.GetReal(
            "Enter PLINTH BEAM WIDTH (must be <= {} m column width)".format(column_width), 
            number=column_width,
            minimum=0.1,
            maximum=2.0
        )
        
        if input_width is None:
            print("Operation cancelled by user.")
            return False
        
        if input_width > column_width:
            print("\n" + "!" * 60)
            print("ERROR: Plinth beam width ({} m) cannot be greater than column width ({} m)".format(
                input_width, column_width))
            print("Please enter a SMALLER or EQUAL value.")
            print("!" * 60 + "\n")
        else:
            beam_width = input_width
            print("Beam width accepted: {} m".format(beam_width))
    
    beam_depth = beam_width * 3.0
    
    Building["structure"]["plinth_beams"]["width"] = beam_width
    Building["structure"]["plinth_beams"]["depth"] = beam_depth
    
    print("Plinth Beam Width: {} m".format(beam_width))
    print("Plinth Beam Depth (auto-calculated): {} m".format(beam_depth))
    print("  [Depth = Width × 3.0 as per DIN 1045 guidelines]")
    print_section_footer()
    
    return True

def get_grid_extension_for_floor(Building, floor_num, hull_coords):
    """
    Ask for grid extension for a SPECIFIC floor - max 3m cantilever.
    Extension is measured from the BOUNDARY (convex hull) of columns.
    """
    max_cantilever = Building["structure"]["plinth_beams"]["max_cantilever"]
    floor_name = "FOUNDATION FLOOR" if floor_num == 1 else "FLOOR {}".format(floor_num)
    
    print_section_header("NOW: Define grid extension for {}".format(floor_name))
    print("Extension is measured from the YELLOW BOUNDARY polyline.")
    print("STRUCTURAL LIMIT: Maximum cantilever = {} m".format(max_cantilever))
    print_section_footer()
    
    extension = rs.GetReal(
        "Enter GRID EXTENSION beyond boundary for {} (max {} m)".format(floor_name, max_cantilever),
        number=2.0,
        minimum=0.0,
        maximum=max_cantilever
    )
    
    if extension is None:
        print("Operation cancelled by user.")
        return None
    
    Building["structure"]["plinth_beams"]["extension_per_floor"].append(extension)
    
    print("Grid Extension for {}: {} m from boundary".format(floor_name, extension))
    print_section_footer()
    
    return extension

def get_additional_floors(Building):
    """After Foundation floor is complete, ask about more floors"""
    print_section_header("FOUNDATION FLOOR COMPLETE!")
    print("Your foundation columns and plinth beams are created.")
    print("Now: Do you want to add more floors above?")
    print_section_footer()
    
    additional_floors = rs.GetInteger(
        "Enter NUMBER OF ADDITIONAL FLOORS to add (0, 1, or 2)",
        number=0,
        minimum=0,
        maximum=2
    )
    
    if additional_floors is None:
        print("Operation cancelled by user.")
        return False
    
    Building["floors"]["num_floors"] = 1 + additional_floors
    
    print("Total Floors: {} (1 foundation + {} additional)".format(
        Building["floors"]["num_floors"], additional_floors))
    print_section_footer()
    
    return True

def get_upper_floor_height(Building, floor_num):
    """Ask for column height of a specific upper floor"""
    print_section_header("FLOOR {} HEIGHT".format(floor_num))
    
    floor_height = rs.GetReal(
        "Enter COLUMN HEIGHT for FLOOR {} (meters)".format(floor_num),
        number=3.0,
        minimum=2.0,
        maximum=6.0
    )
    
    if floor_height is None:
        print("Operation cancelled by user.")
        return None
    
    Building["floors"]["floor_heights"].append(floor_height)
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])
    
    print("Floor {} Column Height: {} m".format(floor_num, floor_height))
    print("Total Building Height so far: {} m".format(Building["floors"]["total_height"]))
    print_section_footer()
    
    return floor_height

# GEOMETRY GENERATION      

def draw_plot_boundary(Building):
    """Draw the plot boundary rectangle."""
    
    plot_length = Building["plot"]["length"]
    plot_width = Building["plot"]["width"]
    
    if not rs.IsLayer("Plot_Boundary"):
        rs.AddLayer("Plot_Boundary", (128, 128, 128))
    
    print_section_header("DRAWING PLOT BOUNDARY")
    
    corners = [
        (-plot_length/2, -plot_width/2, 0),
        (plot_length/2, -plot_width/2, 0),
        (plot_length/2, plot_width/2, 0),
        (-plot_length/2, plot_width/2, 0),
        (-plot_length/2, -plot_width/2, 0)
    ]
    
    boundary = rs.AddPolyline(corners)
    if boundary:
        rs.ObjectLayer(boundary, "Plot_Boundary")
        rs.ObjectColor(boundary, (128, 128, 128))
        Building["plot"]["boundary"] = boundary
        Building["geometry"]["plot_boundary"] = boundary
    
    print("Plot boundary drawn: {} m x {} m".format(plot_length, plot_width))
    print_section_footer()
    
    rs.ZoomExtents()
    rs.Redraw()
    
    return True

def generate_foundation_grid(Building):
    """Generate foundation grid points at Z=0."""
    
    plot_length = Building["plot"]["length"]
    plot_width = Building["plot"]["width"]
    grid_size = Building["grid"]["spacing"]
    
    num_x = int(plot_length / grid_size) + 1
    num_y = int(plot_width / grid_size) + 1
    
    if not rs.IsLayer("Foundation_Grid"):
        rs.AddLayer("Foundation_Grid", (255, 0, 0))
    
    print_section_header("STEP 1: GENERATING FOUNDATION GRID AT Z=0")
    
    foundation_points = []
    
    for i in range(num_x):
        for j in range(num_y):
            x = i * grid_size - plot_length / 2
            y = j * grid_size - plot_width / 2
            z = 0.0
            
            pt = rs.AddPoint(x, y, z)
            if pt:
                rs.ObjectLayer(pt, "Foundation_Grid")
                rs.ObjectColor(pt, (255, 0, 0))
                foundation_points.append(pt)
    
    corners = [
        (-plot_length/2, -plot_width/2, 0),
        (plot_length/2, -plot_width/2, 0),
        (plot_length/2, plot_width/2, 0),
        (-plot_length/2, plot_width/2, 0),
        (-plot_length/2, -plot_width/2, 0)
    ]
    boundary = rs.AddPolyline(corners)
    if boundary:
        rs.ObjectLayer(boundary, "Foundation_Grid")
        rs.ObjectColor(boundary, (255, 0, 0))
    
    Building["grid"]["foundation_points"] = foundation_points
    Building["geometry"]["foundation_grid"] = foundation_points
    
    print("Foundation Grid Points: {} ({}x{})".format(
        len(foundation_points), num_x, num_y))
    print("Grid Spacing: {} m".format(grid_size))
    print_section_footer()
    
    rs.ZoomExtents()
    rs.Redraw()
    
    return True

def select_column_points_floor1(Building):
    """Interactive selection of column points for FLOOR 1"""
    
    print_section_header("STEP 2: SELECT COLUMN POINTS FOR FOUNDATION FLOOR")
    print("Please select the foundation points where you want to place columns.")
    print("Press ENTER when done selecting.")
    print_section_footer()
    
    selected_points = rs.GetObjects(
        "Select foundation points for FOUNDATION columns (Press ENTER when done)", 
        filter=1,
        preselect=False,
        select=True
    )
    
    if not selected_points:
        print("No points selected. Operation cancelled.")
        return False
    
    print("\nSelected {} points for FOUNDATION column placement.".format(len(selected_points)))
    
    for pt_id in selected_points:
        rs.ObjectColor(pt_id, (0, 255, 0))
    
    # Get coordinates
    selected_coords = []
    for pt_id in selected_points:
        coord = rs.PointCoordinates(pt_id)
        if coord:
            selected_coords.append(coord)
    
    Building["grid"]["selected_column_points"] = selected_points
    Building["grid"]["selected_points_per_floor"] = [selected_points]
    Building["grid"]["selected_coords_per_floor"] = [selected_coords]
    
    rs.Redraw()
    
    return True

def create_floor_columns(Building, floor_num, base_z, floor_height, selected_point_coords):
    """Create columns for a SPECIFIC floor."""
    
    column_width = Building["structure"]["columns"]["width"]
    
    if not rs.IsLayer("Columns"):
        rs.AddLayer("Columns", (100, 100, 100))
    
    floor_columns = []
    floor_top_points = []
    
    print("  Creating Floor {} columns (Z={} m to Z={} m)...".format(
        floor_num, base_z, base_z + floor_height))
    
    for pt_coord in selected_point_coords:
        x, y = pt_coord[0], pt_coord[1]
        z = base_z
        half_width = column_width / 2.0
        
        bottom_corners = [
            (x - half_width, y - half_width, z),
            (x + half_width, y - half_width, z),
            (x + half_width, y + half_width, z),
            (x - half_width, y + half_width, z),
            (x - half_width, y - half_width, z)
        ]
        
        bottom_profile = rs.AddPolyline(bottom_corners)
        
        if bottom_profile:
            profile_curve = rs.coercecurve(bottom_profile)
            if profile_curve:
                extrusion = rg.Extrusion.Create(profile_curve, floor_height, True)
                
                if extrusion:
                    column_brep = sc.doc.Objects.AddBrep(extrusion.ToBrep())
                    
                    if column_brep:
                        rs.ObjectLayer(column_brep, "Columns")
                        floor_columns.append(column_brep)
                        
                        top_point = (x, y, z + floor_height)
                        floor_top_points.append(top_point)
            
            rs.DeleteObject(bottom_profile)
    
    print("    Floor {} columns created: {}".format(floor_num, len(floor_columns)))
    
    Building["structure"]["columns"]["objects"].extend(floor_columns)
    Building["structure"]["columns"]["objects_per_floor"].append(floor_columns)
    Building["structure"]["columns"]["top_points_per_floor"].append(floor_top_points)
    
    sc.doc.Views.Redraw()
    
    return floor_top_points

def create_floor_beams_from_boundary(Building, floor_num, floor_top_points, hull_coords, extension):
    """
    Create beams based on the BOUNDARY (convex hull) + extension.
    
    The grid extends from the boundary outward by the extension amount.
    Beams pass through all column positions and extend to boundary + extension.
    """
    
    beam_width = Building["structure"]["plinth_beams"]["width"]
    beam_depth = Building["structure"]["plinth_beams"]["depth"]
    
    if not rs.IsLayer("Wooden_Beam"):
        rs.AddLayer("Wooden_Beam", (139, 69, 19))
    
    if not floor_top_points:
        print("  Floor {}: No column top points for beam creation!".format(floor_num))
        return [], []
    
    beam_z = floor_top_points[0][2]
    
    print("  Creating Floor {} beams at Z={} m...".format(floor_num, beam_z))
    
    floor_beams = []
    
    # Get unique X and Y coordinates from ALL columns (for beam grid lines)
    all_x_coords = sorted(list(set([pt[0] for pt in floor_top_points])))
    all_y_coords = sorted(list(set([pt[1] for pt in floor_top_points])))
    
    # Get boundary extents from HULL COORDINATES (convex hull boundary)
    hull_x = [pt[0] for pt in hull_coords]
    hull_y = [pt[1] for pt in hull_coords]
    
    # Boundary min/max from convex hull
    boundary_min_x = min(hull_x)
    boundary_max_x = max(hull_x)
    boundary_min_y = min(hull_y)
    boundary_max_y = max(hull_y)
    
    # Beam extents = boundary + extension
    beam_min_x = boundary_min_x - extension
    beam_max_x = boundary_max_x + extension
    beam_min_y = boundary_min_y - extension
    beam_max_y = boundary_max_y + extension
    
    print("  Boundary (yellow polyline): X({:.1f} to {:.1f}), Y({:.1f} to {:.1f})".format(
        boundary_min_x, boundary_max_x, boundary_min_y, boundary_max_y))
    print("  Grid extension: {} m from boundary".format(extension))
    print("  Beam extent: X({:.1f} to {:.1f}), Y({:.1f} to {:.1f})".format(
        beam_min_x, beam_max_x, beam_min_y, beam_max_y))
    
    # Create HORIZONTAL beams (along X axis) at each Y coordinate
    for y in all_y_coords:
        start_pt = rg.Point3d(beam_min_x, y, beam_z)
        end_pt = rg.Point3d(beam_max_x, y, beam_z)
        
        beam = create_single_beam(start_pt, end_pt, beam_width, beam_depth)
        if beam:
            rs.ObjectLayer(beam, "Wooden_Beam")
            floor_beams.append(beam)
    
    # Create VERTICAL beams (along Y axis) at each X coordinate
    for x in all_x_coords:
        start_pt = rg.Point3d(x, beam_min_y, beam_z)
        end_pt = rg.Point3d(x, beam_max_y, beam_z)
        
        beam = create_single_beam(start_pt, end_pt, beam_width, beam_depth)
        if beam:
            rs.ObjectLayer(beam, "Wooden_Beam")
            floor_beams.append(beam)
    
    print("    Floor {} beams created: {} ({} horizontal + {} vertical)".format(
        floor_num, len(floor_beams), len(all_y_coords), len(all_x_coords)))
    
    # Calculate ALL intersections for this floor's grid
    all_intersections = []
    for x in all_x_coords:
        for y in all_y_coords:
            all_intersections.append((x, y, beam_z))
    
    Building["structure"]["plinth_beams"]["objects"].extend(floor_beams)
    Building["structure"]["plinth_beams"]["objects_per_floor"].append(floor_beams)
    Building["structure"]["plinth_beams"]["intersection_points_per_floor"].append(all_intersections)
    
    print("    Beam intersections: {}".format(len(all_intersections)))
    
    sc.doc.Views.Redraw()
    
    return floor_beams, all_intersections

def create_single_beam(start_pt, end_pt, beam_width, beam_depth):
    """Helper function to create a single beam between two points."""
    direction = rg.Vector3d(end_pt - start_pt)
    direction.Unitize()
    
    perp_dir = rg.Vector3d(-direction.Y, direction.X, 0)
    perp_dir.Unitize()
    
    half_width = beam_width / 2.0
    
    bottom_corners = [
        start_pt + perp_dir * half_width,
        start_pt - perp_dir * half_width,
        end_pt - perp_dir * half_width,
        end_pt + perp_dir * half_width,
        start_pt + perp_dir * half_width
    ]
    
    bottom_profile = rs.AddPolyline(bottom_corners)
    
    if bottom_profile:
        profile_curve = rs.coercecurve(bottom_profile)
        if profile_curve:
            extrusion = rg.Extrusion.Create(profile_curve, beam_depth, True)
            
            if extrusion:
                beam_brep = sc.doc.Objects.AddBrep(extrusion.ToBrep())
                rs.DeleteObject(bottom_profile)
                return beam_brep
        
        rs.DeleteObject(bottom_profile)
    
    return None

def generate_intersection_grid_from_floor(Building, floor_num, all_intersections):
    """Generate grid points at beam intersections for THIS FLOOR."""
    
    if not all_intersections:
        print("No intersection points for grid generation!")
        return [], 0
    
    beam_depth = Building["structure"]["plinth_beams"]["depth"]
    floor_z = all_intersections[0][2] + beam_depth
    
    layer_name = "Floor_Grid_{}".format(floor_num)
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (0, 0, 255))
    
    print_section_header("GENERATING GRID AT FLOOR {} BEAM INTERSECTIONS (Z={} m)".format(floor_num, floor_z))
    
    grid_point_ids = []
    
    for pt in all_intersections:
        new_pt = (pt[0], pt[1], floor_z)
        pt_id = rs.AddPoint(new_pt)
        if pt_id:
            rs.ObjectLayer(pt_id, layer_name)
            rs.ObjectColor(pt_id, (0, 0, 255))
            grid_point_ids.append(pt_id)
    
    print("Grid Points: {} (at Floor {} beam intersections)".format(len(grid_point_ids), floor_num))
    print_section_footer()
    
    rs.Redraw()
    
    return grid_point_ids, floor_z

def select_columns_for_next_floor(Building, floor_num, grid_point_ids):
    """Let user select which beam intersections should have columns."""
    
    max_cantilever = Building["structure"]["plinth_beams"]["max_cantilever"]
    
    print_section_header("SELECT COLUMNS TO RAISE FOR FLOOR {}".format(floor_num))
    print("The BLUE points show beam intersections from Floor {}.".format(floor_num - 1))
    print("Select which positions you want columns for Floor {}.".format(floor_num))
    print("NOTE: This defines the NEW BOUNDARY for Floor {}.".format(floor_num))
    print("Max cantilever = {} m".format(max_cantilever))
    print("Press ENTER when done selecting.")
    print_section_footer()
    
    selected_points = rs.GetObjects(
        "Select intersection points for FLOOR {} columns (Press ENTER when done)".format(floor_num), 
        filter=1,
        preselect=False,
        select=True
    )
    
    if not selected_points:
        print("No points selected for Floor {}.".format(floor_num))
        return [], []
    
    print("\nSelected {} points for FLOOR {} column placement.".format(len(selected_points), floor_num))
    
    selected_coords = []
    for pt_id in selected_points:
        rs.ObjectColor(pt_id, (0, 255, 0))
        coord = rs.PointCoordinates(pt_id)
        if coord:
            selected_coords.append(coord)
    
    Building["grid"]["selected_points_per_floor"].append(selected_points)
    Building["grid"]["selected_coords_per_floor"].append(selected_coords)
    
    rs.Redraw()
    
    return selected_points, selected_coords

def cleanup_floor_grid(layer_name):
    """Remove temporary floor grid after column selection."""
    if rs.IsLayer(layer_name):
        objs = rs.ObjectsByLayer(layer_name)
        if objs:
            rs.DeleteObjects(objs)
        rs.DeleteLayer(layer_name)

def process_foundation_floor(Building):
    """Process FOUNDATION FLOOR (Floor 1)"""
    
    print_section_header("STEP 3: BUILDING FOUNDATION FLOOR")
    
    floor_height = Building["structure"]["columns"]["height"]
    selected_coords = Building["grid"]["selected_coords_per_floor"][0]
    
    # Create Foundation columns
    floor_top_points = create_floor_columns(Building, 1, 0.0, floor_height, selected_coords)
    
    # Create boundary (yellow points + polyline at convex hull)
    column_top_z = floor_height
    boundary, hull_coords = create_boundary_from_columns(Building, 1, floor_top_points, column_top_z)
    
    # Cleanup foundation grid
    print("  Cleaning up foundation grid...")
    if rs.IsLayer("Foundation_Grid"):
        objs = rs.ObjectsByLayer("Foundation_Grid")
        if objs:
            rs.DeleteObjects(objs)
    
    sc.doc.Views.Redraw()
    
    # Ask for beam width
    if not get_plinth_beam_width(Building):
        return None, None, None
    
    # Ask for grid extension (from boundary)
    extension = get_grid_extension_for_floor(Building, 1, hull_coords)
    if extension is None:
        return None, None, None
    
    # Create beams (extending from boundary + extension)
    floor_beams, all_intersections = create_floor_beams_from_boundary(
        Building, 1, floor_top_points, hull_coords, extension)
    
    print_section_footer()
    
    return floor_top_points, all_intersections, hull_coords

def process_upper_floor(Building, floor_num, previous_intersections, floor_height):
    """Process an UPPER floor (2 or 3)"""
    
    print_section_header("PROCESSING FLOOR {}".format(floor_num))
    
    beam_depth = Building["structure"]["plinth_beams"]["depth"]
    
    # Generate grid at previous floor's intersections
    grid_layer = "Floor_Grid_{}".format(floor_num - 1)
    grid_points, grid_z = generate_intersection_grid_from_floor(
        Building, floor_num - 1, previous_intersections)
    
    # User selects columns
    selected_points, selected_coords = select_columns_for_next_floor(Building, floor_num, grid_points)
    
    if not selected_coords:
        print("No columns selected for Floor {}. Skipping.".format(floor_num))
        cleanup_floor_grid(grid_layer)
        return [], [], []
    
    # Create columns
    current_z = grid_z
    floor_top_points = create_floor_columns(Building, floor_num, current_z, floor_height, selected_coords)
    
    # Create boundary (yellow points + polyline at convex hull)
    column_top_z = current_z + floor_height
    boundary, hull_coords = create_boundary_from_columns(Building, floor_num, floor_top_points, column_top_z)
    
    # Cleanup grid
    cleanup_floor_grid(grid_layer)
    
    # Ask for extension (from new boundary)
    extension = get_grid_extension_for_floor(Building, floor_num, hull_coords)
    if extension is None:
        extension = 0
    
    # Create beams (extending from new boundary + extension)
    floor_beams, all_intersections = create_floor_beams_from_boundary(
        Building, floor_num, floor_top_points, hull_coords, extension)
    
    print_section_footer()
    
    return floor_top_points, all_intersections, hull_coords

# MAIN EXECUTION      
def main():
    """Main execution function."""
    
    clear_plot()
    Building = initialize_building_data()
    
    # ============ PHASE 1: FOUNDATION FLOOR ============
    
    if not get_plot_dimensions(Building):
        return None
    
    if not draw_plot_boundary(Building):
        return None
    
    if not get_grid_spacing(Building):
        return None
    
    if not generate_foundation_grid(Building):
        return None
    
    if not get_column_inputs(Building):
        return None
    
    if not select_column_points_floor1(Building):
        return None
    
    result = process_foundation_floor(Building)
    if result[0] is None:
        return None
    foundation_top_points, foundation_intersections, _ = result
    
    # ============ PHASE 2: ADDITIONAL FLOORS ============
    
    if not get_additional_floors(Building):
        return None
    
    num_floors = Building["floors"]["num_floors"]
    previous_intersections = foundation_intersections
    
    for floor_num in range(2, num_floors + 1):
        if not previous_intersections:
            print("Cannot continue - no intersections from previous floor!")
            break
        
        floor_height = get_upper_floor_height(Building, floor_num)
        if floor_height is None:
            return None
        
        result = process_upper_floor(
            Building, floor_num, previous_intersections, floor_height)
        _, previous_intersections, _ = result
    
    # ============ FINAL SUMMARY ============
    
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])
    rs.ZoomExtents()
    
    print_section_header("GENERATION COMPLETE!")
    print("Number of Floors: {}".format(Building["floors"]["num_floors"]))
    print("Floor Heights: {}".format(Building["floors"]["floor_heights"]))
    print("Extensions per Floor: {}".format(Building["structure"]["plinth_beams"]["extension_per_floor"]))
    print("Max Cantilever: {} m".format(Building["structure"]["plinth_beams"]["max_cantilever"]))
    print("Total Building Height: {} m".format(Building["floors"]["total_height"]))
    print("\nStructure Summary:")
    
    cols_per_floor = Building["structure"]["columns"]["objects_per_floor"]
    beams_per_floor = Building["structure"]["plinth_beams"]["objects_per_floor"]
    extensions = Building["structure"]["plinth_beams"]["extension_per_floor"]
    
    for i in range(len(cols_per_floor)):
        col_count = len(cols_per_floor[i])
        beam_count = len(beams_per_floor[i]) if i < len(beams_per_floor) else 0
        ext = extensions[i] if i < len(extensions) else 0
        floor_name = "Foundation" if i == 0 else "Floor {}".format(i + 1)
        print("  {}: {} columns, {} beams, {} m extension".format(floor_name, col_count, beam_count, ext))
    
    print("\nTotal Columns: {}".format(len(Building["structure"]["columns"]["objects"])))
    print("Total Beams: {}".format(len(Building["structure"]["plinth_beams"]["objects"])))
    print_section_footer()
    
    print("\nFINAL BUILDING DATA STRUCTURE:")
    print("=" * 60)
    pprint.pprint(Building)
    print("=" * 60)
    
    return Building

if __name__ == "__main__":
    Building_data = main()
